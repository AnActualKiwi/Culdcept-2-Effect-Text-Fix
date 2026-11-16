param(
    [Parameter(Position = 0)]
    [string]$IsoPath,

    [string]$PatchPath
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($PatchPath)) {
    $PatchPath = Join-Path $PSScriptRoot "patches\culdcept-usa-effect-text-fix.cdp"
}

function Stop-WithMessage {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Get-FileSha256 {
    param([string]$Path)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $bytes = $sha.ComputeHash($stream)
        return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

function Read-Hash {
    param([System.IO.BinaryReader]$Reader, [string]$Name)

    $bytes = $Reader.ReadBytes(32)
    if ($bytes.Length -ne 32) {
        throw "The patch is truncated while reading the $Name hash."
    }
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Read-PatchHeader {
    param([string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    $reader = New-Object System.IO.BinaryReader($stream)
    try {
        $magic = [System.Text.Encoding]::ASCII.GetString($reader.ReadBytes(4))
        if ($magic -ne "CDP1") {
            throw "This is not a Culdcept CDP1 patch."
        }

        $version = $reader.ReadUInt16()
        $flags = $reader.ReadUInt16()
        $sourceSize = $reader.ReadUInt64()
        $targetSize = $reader.ReadUInt64()
        $sourceHash = Read-Hash -Reader $reader -Name "source"
        $targetHash = Read-Hash -Reader $reader -Name "target"
        $segments = $reader.ReadUInt32()

        if ($version -ne 1) {
            throw "Unsupported patch version: $version"
        }
        if ($flags -ne 0) {
            throw "Unsupported patch flags: $flags"
        }
        if ($sourceSize -eq 0 -or $targetSize -eq 0) {
            throw "The patch contains an invalid image size."
        }
        if ($segments -eq 0 -or $segments -gt 1000000) {
            throw "The patch contains an invalid byte-range count."
        }

        return [pscustomobject]@{
            SourceSize = [uint64]$sourceSize
            TargetSize = [uint64]$targetSize
            SourceHash = $sourceHash
            TargetHash = $targetHash
            Segments   = [uint32]$segments
        }
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Test-PatchLayout {
    param([string]$Path, $Header)

    $stream = [System.IO.File]::OpenRead($Path)
    $reader = New-Object System.IO.BinaryReader($stream)
    try {
        $stream.Position = 92
        $previousEnd = [uint64]0

        for ($i = 0; $i -lt [int]$Header.Segments; $i++) {
            if ($stream.Position + 20 -gt $stream.Length) {
                throw "The patch is truncated at byte range $i."
            }

            $offset = [uint64]$reader.ReadUInt64()
            $rawLength = [uint64]$reader.ReadUInt64()
            $compressedLength = [uint64]$reader.ReadUInt32()

            if ($rawLength -eq 0) {
                throw "Byte range $i has zero length."
            }
            if ($compressedLength -eq 0 -or $compressedLength -gt 1073741824) {
                throw "Byte range $i has an invalid compressed length."
            }
            if ($offset -lt $previousEnd) {
                throw "Byte ranges overlap or are out of order."
            }
            if (($offset + $rawLength) -gt $Header.TargetSize) {
                throw "Byte range $i extends past the target image."
            }
            if (($stream.Position + [int64]$compressedLength) -gt $stream.Length) {
                throw "The patch is truncated inside byte range $i."
            }

            $previousEnd = $offset + $rawLength
            $stream.Seek([int64]$compressedLength, [System.IO.SeekOrigin]::Current) | Out-Null
        }

        if ($stream.Position -ne $stream.Length) {
            throw "The patch has trailing data."
        }
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Expand-Zlib {
    param([byte[]]$Data, [uint64]$ExpectedLength, [int]$Index)

    if ($Data.Length -lt 6) {
        throw "Byte range $Index is too short to contain zlib data."
    }

    $compressed = New-Object byte[] ($Data.Length - 6)
    [System.Array]::Copy($Data, 2, $compressed, 0, $compressed.Length)

    $input = New-Object System.IO.MemoryStream
    $output = New-Object System.IO.MemoryStream
    $deflate = New-Object System.IO.Compression.DeflateStream(
        $input,
        [System.IO.Compression.CompressionMode]::Decompress
    )
    try {
        $input.Write($compressed, 0, $compressed.Length)
        $input.Position = 0
        $buffer = New-Object byte[] 1048576
        while (($read = $deflate.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $output.Write($buffer, 0, $read)
        }
        $result = $output.ToArray()
    }
    finally {
        $deflate.Dispose()
        $input.Dispose()
        $output.Dispose()
    }

    if ([uint64]$result.Length -ne $ExpectedLength) {
        throw "Byte range $Index expands to an unexpected size."
    }
    return ,$result
}

function Apply-Patch {
    param([string]$Source, [string]$Patch)

    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        Stop-WithMessage "The ISO was not found: $Source"
    }
    if (-not (Test-Path -LiteralPath $Patch -PathType Leaf)) {
        Stop-WithMessage "The patch was not found: $Patch"
    }

    $header = Read-PatchHeader -Path $Patch
    Test-PatchLayout -Path $Patch -Header $header

    $sourceFull = [System.IO.Path]::GetFullPath($Source)
    $sourceItem = Get-Item -LiteralPath $sourceFull
    if ([uint64]$sourceItem.Length -ne $header.SourceSize) {
        Stop-WithMessage ("This ISO is not the required pristine image.`n" +
            "Expected {0:N0} bytes, found {1:N0} bytes." -f $header.SourceSize, $sourceItem.Length)
    }

    Write-Host "Checking the source ISO..."
    $sourceHash = Get-FileSha256 -Path $sourceFull
    if ($sourceHash -ne $header.SourceHash) {
        Stop-WithMessage ("The source image SHA-256 does not match.`n" +
            "Expected $($header.SourceHash)`nFound    $sourceHash")
    }

    $sourceDirectory = [System.IO.Path]::GetDirectoryName($sourceFull)
    $sourceBase = [System.IO.Path]::GetFileNameWithoutExtension($sourceFull)
    $output = Join-Path $sourceDirectory ($sourceBase + " patched.iso")
    $temporary = $output + ".part"

    if ([System.IO.Path]::GetFullPath($output) -eq $sourceFull) {
        Stop-WithMessage "The output path would overwrite the source ISO."
    }
    if (Test-Path -LiteralPath $output) {
        Stop-WithMessage "The output already exists: $output`nDelete it or rename the source ISO."
    }
    if (Test-Path -LiteralPath $temporary) {
        Stop-WithMessage "A previous partial output exists: $temporary`nDelete it and try again."
    }

    Write-Host "Copying the source image..."
    try {
        $sourceStream = [System.IO.File]::OpenRead($sourceFull)
        $outputStream = [System.IO.File]::Open(
            $temporary,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        try {
            $sourceStream.CopyTo($outputStream, 8388608)
        }
        finally {
            $sourceStream.Dispose()
            $outputStream.Dispose()
        }
    }
    catch {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        }
        throw
    }

    try {
        Write-Host "Applying byte ranges..."
        $outputStream = [System.IO.File]::Open(
            $temporary,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        $patchStream = [System.IO.File]::OpenRead($Patch)
        $reader = New-Object System.IO.BinaryReader($patchStream)
        try {
            $patchStream.Position = 92
            for ($i = 0; $i -lt [int]$header.Segments; $i++) {
                $offset = [uint64]$reader.ReadUInt64()
                $rawLength = [uint64]$reader.ReadUInt64()
                $compressedLength = [uint64]$reader.ReadUInt32()
                $compressed = $reader.ReadBytes([int]$compressedLength)
                if ($compressed.Length -ne [int]$compressedLength) {
                    throw "The patch is truncated inside byte range $i."
                }

                [byte[]]$data = Expand-Zlib -Data $compressed -ExpectedLength $rawLength -Index $i
                $outputStream.Position = [int64]$offset
                $outputStream.Write($data, 0, $data.Length)

                if (($i + 1) % 50 -eq 0 -or ($i + 1) -eq [int]$header.Segments) {
                    Write-Host ("  {0}/{1}" -f ($i + 1), $header.Segments)
                }
            }
            $outputStream.SetLength([int64]$header.TargetSize)
            $outputStream.Flush()
        }
        finally {
            $reader.Dispose()
            $patchStream.Dispose()
            $outputStream.Dispose()
        }

        $outputItem = Get-Item -LiteralPath $temporary
        if ([uint64]$outputItem.Length -ne $header.TargetSize) {
            throw "The output image has an unexpected size."
        }

        Write-Host "Checking the patched image..."
        $outputHash = Get-FileSha256 -Path $temporary
        if ($outputHash -ne $header.TargetHash) {
            throw ("The output SHA-256 does not match.`n" +
                "Expected $($header.TargetHash)`nFound    $outputHash")
        }

        [System.IO.File]::Move($temporary, $output)
        Write-Host ""
        Write-Host "Patch applied successfully." -ForegroundColor Green
        Write-Host "Output: $output"
        Write-Host "SHA-256: $outputHash"
    }
    catch {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

try {
    if ([string]::IsNullOrWhiteSpace($IsoPath)) {
        $IsoPath = Read-Host "Path to the pristine Culdcept (USA) ISO"
    }
    $IsoPath = $IsoPath.Trim().Trim('"')
    $PatchPath = $PatchPath.Trim().Trim('"')

    if ([string]::IsNullOrWhiteSpace($IsoPath)) {
        Stop-WithMessage "No ISO was supplied."
    }

    Write-Host ""
    Write-Host "Culdcept 2 Effect Text Fix" -ForegroundColor Cyan
    Write-Host ""
    Apply-Patch -Source $IsoPath -Patch $PatchPath
    exit 0
}
catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    exit 1
}
