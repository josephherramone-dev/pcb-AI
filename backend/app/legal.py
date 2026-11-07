"""Legal notices shown in the UI, returned by the API and written into exported projects.

Single source of truth so the wording is identical everywhere. These texts are
product notices, not legal advice; see docs/legal/LEGAL.md for the review checklist.
"""

from __future__ import annotations

ENGINEERING_DISCLAIMER = (
    "This software and every design, file and report it produces are provided \"as is\", without "
    "warranty of any kind. Passing the platform's checks (including KiCad ERC/DRC) does not mean a "
    "design is correct, safe, reliable or compliant with any standard or regulation. You are solely "
    "responsible for independent engineering review, testing and any certification (for example "
    "electrical safety, EMC/FCC/CE) before manufacturing, selling or using a design. Do not rely on "
    "this software for safety-critical, medical, automotive, aerospace or life-support applications."
)

AI_DISCLOSURE = (
    "The design assistant is an AI system (Claude, by Anthropic) accessed through the Anthropic API. "
    "Your messages, the current design and its check results are sent to Anthropic to generate "
    "answers. AI output can be wrong or incomplete: proposals are validated only against the KiCad "
    "libraries and are never applied without your approval. Do not enter personal or confidential "
    "data you are not allowed to share with this provider."
)

KICAD_LIBRARY_NOTICE = (
    "Schematic symbols and footprints come from the official KiCad libraries (c) KiCad Community, "
    "licensed under CC BY-SA 4.0 with the following exception: \"To the extent that the creation of "
    "electronic designs that use 'Licensed Material' can be considered to be 'Adapted Material', then "
    "the copyright holder waives article 3 of the license with respect to these designs and any "
    "generated files which use data provided as part of the 'Licensed Material'.\" "
    "The full license text ships with the KiCad libraries (https://kicad.github.io/symbols/, "
    "https://kicad.github.io/footprints/)."
)

ATTRIBUTIONS = [
    {
        "name": "KiCad EDA",
        "role": "EDA engine (kicad-cli, pcbnew) run as a separate program",
        "license": "GPL-3.0-or-later",
        "url": "https://www.kicad.org",
    },
    {
        "name": "KiCad symbol and footprint libraries",
        "role": "Component symbols and footprints",
        "license": "CC-BY-SA-4.0 with design exception",
        "url": "https://kicad.github.io/symbols/",
    },
    {
        "name": "Claude by Anthropic",
        "role": "AI assistant via the Anthropic API (optional)",
        "license": "Anthropic Commercial Terms of Service and Usage Policy",
        "url": "https://www.anthropic.com/legal",
    },
]

NOT_AFFILIATED = (
    "KiCad is a trademark of the KiCad project; Claude and Anthropic are trademarks of Anthropic, PBC. "
    "This product is not affiliated with or endorsed by either."
)


def export_notice(project_name: str, revision_number: int, check_statuses: dict[str, str],
                  kicad_version: str | None) -> str:
    """NOTICE.txt included in every exported project archive."""
    checks = "\n".join(f"  - {name}: {status}" for name, status in sorted(check_statuses.items())) or "  (none)"
    return (
        f"Project: {project_name}\n"
        f"Revision: #{revision_number}\n"
        f"Generated with KiCad {kicad_version or 'unknown'} by the PCB AI platform.\n\n"
        f"Checks run on this revision at export time:\n{checks}\n"
        "Raw KiCad reports, where available, are in the reports/ folder.\n\n"
        "IMPORTANT - NO WARRANTY\n"
        f"{ENGINEERING_DISCLAIMER}\n\n"
        "LIBRARY ATTRIBUTION\n"
        f"{KICAD_LIBRARY_NOTICE}\n\n"
        f"{NOT_AFFILIATED}\n"
    )


def legal_info() -> dict:
    return {
        "engineering_disclaimer": ENGINEERING_DISCLAIMER,
        "ai_disclosure": AI_DISCLOSURE,
        "kicad_library_notice": KICAD_LIBRARY_NOTICE,
        "attributions": ATTRIBUTIONS,
        "not_affiliated": NOT_AFFILIATED,
        "third_party_notices": "THIRD_PARTY_NOTICES.md in the source repository",
    }
