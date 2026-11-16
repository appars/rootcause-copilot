# Day 4 Student Worksheet - RootCause Copilot

Name: ____________________  USN: ____________  Mode used: ☐ Demo ☐ Live AI

## A. Setup checklist

- [ ] `git --version` works: version ________
- [ ] `python --version` (or `py --version`) works: version ________
- [ ] Repository cloned, `cd rootcause-copilot`
- [ ] Virtual environment active - prompt starts with `(.venv)`
- [ ] `python -c "import sys; print(sys.executable)"` ends in `.venv\Scripts\python.exe`
- [ ] `python -m pip install -r requirements.txt` finished without errors
- [ ] App opens at http://localhost:8501 (or port ______)
- [ ] Groq key connected in the sidebar (🟢 Connected) - or working in Demo Mode. **Never write the key down here.**

## B. Investigation tasks (simulated alert: payment service)

1. **Event (Concept 4).** What does the *Incident Received* step in the **Execution trace** say about the trigger, and why is it SIMULATED?
   ______________________________________________
2. **Evidence.** Number of log lines ____, errors ____, warnings ____, time window ______ to ______.
   Top two patterns: ______________ (____ lines), ______________ (____ lines)
3. **Context (Concept 2).** Characters used ______ of ______. Log lines selected ____ of ____.
   One thing that was collapsed, truncated or excluded: ______________________________
4. **Decisions (Concept 3).** From the Execution trace: which steps were *Completed*, which *Skipped* (and why)? List the tools in order and who selected each:
   1. ______________ 2. ______________ 3. ______________ 4. ______________ 5. ______________
5. **Memory (Concept 1).** Top similar incident: ____________ score ____ . Matched on: ____________
   Why does `HIST-2025-090` (same service) rank lower? ______________________________
6. **Reflection (Concept 5).** Evidence label in round 1 ______________ → final label ______________.
   Which step of the trace had origin **SIMULATED DEMO RESULT** (if you used Demo Mode)? ______________
   Which check failed in round 1? ______________________________
   What changed in the revised hypothesis? ______________________________
7. **Approval (Concept 7).** Proposed action: ______________________ Risk level: ______ Requires approval? ☐ yes ☐ no
   What happened when you clicked *Reject* without a rationale? ______________________________
   What does the *Execution* column say after approval? ______________________________
8. **Error recovery (Concept 6).**
   - Transient failure: attempts for `search_knowledge_base` ____ ; status ______
   - Persistent failure: did the investigation complete? ☐ yes ☐ no. Where is the missing evidence reported? ______
   - `corrupt_report.pdf` status in the Knowledge Base: ______
9. **Persistence.** After restarting the app: is your incident in History? ☐ yes ☐ no.
   Is your API key still set? ☐ yes ☐ no. Explain the difference: ______________________________

## C. Observations to record

| Question | Your observation |
|---|---|
| Which numbers came from deterministic code? | |
| Which text came from the model / demo output? | |
| One limitation the app admitted honestly | |
| One thing you would add for a real company | |

## D. Mini challenge (CHALLENGE-01 - submit via HOMEWORK_SUBMISSION.md, Part A)

Root-cause hypothesis: ______________________________________________
Key evidence (line numbers / incident IDs): ______________________________
Corrective action + risk: ______________________________

### Optional code extension

Challenge chosen (1-4 from the hands-on guide): ____  File(s) changed: ______________________
Test added / result of `python -m pytest`: ______________________

## E. Exit ticket / interview questions

1. Persistent memory vs. context management - one sentence each.
2. What prevents the agent from calling a tool that deletes data?
3. Why is "retry 3 times" not the same as "recover"?
4. Give one reason a human must approve a production restart.
5. What is the biggest risk of trusting an LLM's root-cause hypothesis, and how does this app reduce it?
