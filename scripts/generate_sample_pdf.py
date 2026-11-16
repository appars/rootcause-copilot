"""Regenerate data/sample_documents/sre_oncall_handbook.pdf (FICTIONAL training document).

Run from the repository root:  python scripts/generate_sample_pdf.py
"""
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

OUT = Path(__file__).resolve().parent.parent / "data" / "sample_documents" / "sre_oncall_handbook.pdf"

SECTIONS = [
    ("SRE On-Call Handbook (FICTIONAL training document)",
     "This handbook is synthetic material for the RootCause Copilot workshop. It describes general "
     "on-call practice and does not describe any real company."),
    ("1. First five minutes",
     "Acknowledge the alert. Check the customer impact (error rate, latency, failed checkouts). "
     "Open an incident channel and name an incident commander. Do not change anything yet."),
    ("2. Collect evidence before acting",
     "Look at logs for the incident window, recent changes (deployments, configuration, feature flags), "
     "resource usage (CPU, memory), dependency health and similar past incidents. Write down facts and "
     "hypotheses separately."),
    ("3. Production changes need approval",
     "Restarts, scaling, rollbacks, configuration changes and failovers are production changes. "
     "The incident commander approves them, and every decision is recorded with who, what, when and why. "
     "Automated assistants may recommend actions but must not execute them without approval."),
    ("4. Prefer reversible mitigations",
     "Choose the smallest, most reversible action first: pause a batch job, roll back one release, "
     "restart one replica at a time. Know the rollback before you act."),
    ("5. After the incident",
     "Record root cause, resolution and lessons learned so that the next on-call engineer can find them. "
     "A searchable incident history shortens future investigations."),
]


def main() -> None:
    pdf = FPDF(format="A4")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    for i, (title, body) in enumerate(SECTIONS):
        pdf.set_font("Helvetica", "B", 15 if i == 0 else 12)
        pdf.multi_cell(width, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(width, 5.5, body, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(3)
    pdf.output(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
