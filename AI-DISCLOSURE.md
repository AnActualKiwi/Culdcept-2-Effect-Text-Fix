## History

I am entirely self taught when it comes to coding and have a basic understanding of C++ & Python, and the ability to read assembly, though without much understanding.
I started this project back in 2023 and was able to make proof of concept of the new text being implemented but this was as far as my skill could take me.

I quickly ran into concerns about injecting custom mips assembly and dealing with pointer tables and code caves and by this point this was my first official coding project.
Ultimately I shelved the project as I didn't have the time to continue learning programming as a hobby and I was certain someone else would take on this idea.

When the hype around decomps & recomps through Claude started surfacing I was keeping a watchful eye on the space as the potential for modding seemed quite interesting.
Later down the line I decided to trial a free tool - Freebuff for use with basic projects and to test the waters and see if I can develop personal small scale projects.
This snowballed once I realized how far AI agents have come & I made the decision to make the Culdcept patch a reality.

# AI Disclosure 

A strong Majority of the work was completed by the AI with constant oversight over the course of 2 weeks.
I would monitor Freebuff & give specific commands referencing memory I was able to find live in PCSX2 & using Ghidra functions partially decompiled by Freebuff.
The below is a rundown from the latest context window of the AI who I've directed to provide their input on the project.

**Project:** Culdcept 2 Effect Text Fix  

## Purpose and scope

This document describes the involvement of an AI coding agent in the standalone
Culdcept 2 Effect Text Fix repository and its `1.0.0` release. The agent was
Freebuff, a coding agent operating within Codebuff, working under the direction
of the repository owner.

The standalone release packages changes that already existed in the wider
Culdcept PS2 re-translation project. This document does not attempt to catalogue
every AI interaction in that wider project. It records the AI work that produced
and published this repository, and identifies the decisions and verification
that remained with the human owner.

## Summary

The AI wrote or edited the patch tooling, Windows launcher, packaging scripts,
and draft documentation. It generated the binary patch from a supplied pristine
ISO and a supplied finished ISO, ran offline and byte-level checks, built the
release ZIP, and carried out GitHub operations under the owner's direction.

The human owner supplied the game images, made the design and acceptance
decisions, performed or relied on the project's prior in-game verification,
reviewed the release, authorized publication, and is responsible for legal and
licensing decisions. The AI did not independently verify the patched game in
PCSX2 or on a console. This release did not generate new game text, artwork, or
design decisions; it packages an existing finished image.

## Division of work

| Area | AI involvement | Human involvement |
|---|---|---|
| Game translation and game-design decisions | None in this release; the patch reproduces a pre-existing finished image | Supplied and approved the underlying project work; made design and acceptance decisions |
| Patch extraction | Wrote the diff/patch builder and generated the release patch from the supplied images | Supplied the pristine and finished ISOs; owns the source material |
| Windows launcher and patcher | Wrote `Apply Patch.cmd` and `apply_patch.ps1` | Reviewed and tested the release workflow; approved publication |
| Python applier and builder | Wrote `culdcept_patch.py` and `make_patch.py` | Reviewed the resulting behavior and release output |
| README and release copy | Drafted earlier public-facing text | Edited the current README and owns the final wording; the AI was instructed not to modify it further |
| Verification | Ran source/output hash checks, synthetic round-trips, extracted-ZIP tests, and refusal tests | Owned the prior in-game evidence and final acceptance of the game build |
| Git and GitHub operations | Created commits, pushed, created the release, uploaded the asset, removed the earlier release/tag, and rewrote history after approval | Authorized publication, release removal, and the history rewrite |
| Licensing and legal compliance | Provided no legal advice | Responsible for copyright, licensing, and distribution decisions |

## What the AI did

- Authored the standalone patch applier and maintainer-side patch builder.
- Generated the binary patch by comparing the supplied pristine ISO with the
  supplied finished ISO. The patch stores only differing byte ranges and the
  target tail; it does not contain a complete disc image.
- Authored the Windows drag-and-drop launcher and its PowerShell implementation.
  The launcher requires no Python installation and uses PowerShell included with
  Windows 10/11.
- Built the release ZIP and verified that it contains only the launcher, patch
  data, checksums, README, and license.
- Tested the extracted release package against the pristine ISO. The produced
  image matched the finished image byte-for-byte at the SHA-256 level.
- Added safeguards that reject a wrong source image, an already-patched image,
  an existing output file, or an attempted output path collision with the source
  or patch file.
- Drafted earlier public-facing README and release-notes text. The current
  README was subsequently edited by the repository owner; the AI did not modify
  it after that instruction.
- Performed repository and release operations at the owner's direction,
  including force-pushing the single clean root commit and moving the `v1.0.0`
  tag and release to it.

## What the human did

- Supplied the pristine USA ISO and the finished project image used to generate
  the patch.
- Accepted and supplied the underlying game changes used by the release.
- Owned the final design, acceptance criteria, and publication decisions.
- Performed or retained the project's prior in-game verification. The AI's
  standalone release testing was limited to file integrity and byte equality.
- Reviewed and approved the public release.
- Authorized the removal of the earlier release/tag and the repository history
  rewrite.
- Edited and owns the current README wording.
- Holds responsibility for owning legal copies of the game and for complying
  with copyright, licensing, and distribution requirements.

## Verification performed

The AI verified the release mechanically:

- The source ISO matched the expected pristine image size and SHA-256.
- The generated output matched the finished image exactly:
  - **Size:** 4,292,116,480 bytes
  - **SHA-256:** `384ea90fed3037978a64b06e25747b1f79c3850764b1129a0fe364e66a5c0f06`
- The release ZIP's public download was checked against:
  - **Size:** 42,680,060 bytes
  - **SHA-256:** `73b040adb613a669c87b2bc8913b14d656fb6a00a6a83108ebd53248bfce46fd`
- Synthetic patch round-trips passed, including rejection of an altered source.
- The extracted release ZIP was run against the pristine ISO and produced the
  expected hash.
- The AI did **not** run PCSX2 or a console test. Byte equality with the finished
  image is not independent proof of gameplay, timing, or every in-game
  interaction.

The published asset is:

`Culdcept-USA-Effect-Text-Fix-v1.0.0.zip`

## Limitations and disclaimer

- AI-generated code and documentation can contain mistakes. The owner should
  review the tool and release before relying on them.
- The patch is intended only for the specified USA release of the game and only
  for a legally owned copy.
- This document is not legal advice and does not determine ownership of the
  game, its text, or derivative patch data.
- The AI's verification establishes byte-level reproducibility of the supplied
  finished image. It does not establish that every game screen, card, or
  interaction was tested in this release.
- The repository's GPL-2.0 license applies to the repository's code; third-party
  game content remains subject to its own rights.
