# Homework Submission - RootCause Copilot v1.1 (Day 4 challenge + Day 5 deployment)

Name: ____________________  USN: ____________  Date: ____________

> 🔐 **Security warning.** Do **not** include API keys, Docker Hub passwords or tokens, the ArgoCD admin password,
> kubeconfig files, `.env` files or Secret YAML/values - not in screenshots, not in repositories, not in this file.
> Crop or blur anything that looks like a credential. Base64 is not encryption.
> Submissions containing credentials lose marks and must rotate (replace) the leaked credential.

## Submission format

- One ZIP named `<USN>_RootCause_Homework.zip` containing:
  `PartA_challenge.pdf` (or `.md`), the downloaded investigation report, `PartB_day5.pdf` (or `.md`), and a
  `screenshots/` folder (PNG/JPG). Repository links go into the documents - do not zip your repositories.
- Screenshots must show the relevant window clearly; crop personal information and credentials.
- State the mode you used (Live AI Mode or Demo Mode) on every screenshot caption.

---

## Part A - Day 4 mini challenge

**Challenge: Investigate an unfamiliar incident (CHALLENGE-01, search service) and justify your root-cause
hypothesis using evidence from logs and historical incidents.**

| # | Deliverable | Required |
|---|---|---|
| A1 | Investigation screenshot (Execution trace tab visible, mode banner visible) | Mandatory |
| A2 | Root-cause hypothesis in your own words (3-5 sentences): *what changed, what mechanism, what impact* | Mandatory |
| A3 | Supporting evidence: log line numbers (`L..`), the past incident ID(s) you relied on, Kubernetes findings | Mandatory |
| A4 | At least one alternative explanation you **ruled out**, with the evidence that rules it out | Mandatory |
| A5 | Recommended corrective action, its risk level and whether it needs approval (and why) | Mandatory |
| A6 | Downloaded investigation report (PDF or Markdown) | Mandatory |
| A7 | Optional code extension (diff/screenshot + passing `python -m pytest`) | Optional |

**Evaluation (Part A, 10 marks):** correct trigger and mechanism (3) · evidence cited precisely (3) · alternative
ruled out with evidence (2) · safe, reversible action with approval reasoning (2). In Demo Mode the app gives only a
rule-based, *partial* answer for this incident - marks are for **your** reasoning, not the app's text.

---

## Part B - Day 5 deployment homework

## 1. Links

| Item | Value |
|---|---|
| Application repository URL (your fork/clone on GitHub) | |
| GitOps repository URL (`rootcause-copilot-gitops`) | |
| Docker Hub image (`user/rootcause-copilot`) and tags | |

## 2. Evidence checklist

Tick what you completed **yourself**. Mark anything taken from the instructor demo or a shared environment as such.
Items 1-3 and 8 are **mandatory**; items 4-7 are **mandatory if your laptop can run Kubernetes**, otherwise use the
fallback path (section 4).

| # | Evidence | Done by me | From demo / shared | Not done |
|---|---|---|---|---|
| 1 | Screenshot: app running locally (Day 4, Python venv) | ☐ | ☐ | ☐ |
| 2 | Screenshot: `docker build` finished **or** `docker image ls` showing the image | ☐ | ☐ | ☐ |
| 3 | Screenshot: container running (`docker ps`) + app in browser showing *Version day4-v1* | ☐ | ☐ | ☐ |
| 4 | Screenshot: `kubectl -n rootcause get pods,svc,pvc` (pod Running, PVC Bound) | ☐ | ☐ | ☐ |
| 5 | Screenshot: ArgoCD application *Synced* and *Healthy* | ☐ | ☐ | ☐ |
| 6 | Screenshot or short explanation: **OutOfSync → Synced** after changing `newTag` to `day5-v2` | ☐ | ☐ | ☐ |
| 7 | Evidence that incident memory persists (after app restart / container restart / pod deletion) | ☐ | ☐ | ☐ |
| 8 | Architecture diagram in your own words (Docker → registry → Git → ArgoCD → Kubernetes) | ☐ | ☐ | ☐ |

## 3. Environment limitations

Describe your laptop (RAM, CPU, Windows version) and anything that blocked you (virtualization disabled, WSL
missing, proxy, disk). State which steps were **completed**, which were **simulated/documented only**, and why.

______________________________________________________________________________

## 4. Partial-credit / fallback path

If you could not run Kubernetes locally, submit as many of these as possible:

1. Day 4 app running + persistence evidence.
2. Docker build/run evidence (any machine with Docker or Rancher Desktop without Kubernetes).
3. Your GitOps repository with correctly edited manifests and `kustomization.yaml`
   (+ `kubectl kustomize apps\rootcause-copilot` output if kubectl is available).
4. Your own architecture diagram and explanation.
5. Instructor-demo screenshots **clearly labelled** "instructor demo" with your explanation of each step.

## 5. Evaluation expectations (Part B, 20 marks)

| Area | Marks | Full marks when |
|---|---|---|
| Container | 5 | image built with a versioned tag, runs locally, pushed and **pulled back** successfully |
| Kubernetes | 5 | pod Running, PVC Bound, Service reachable, memory survives a pod restart (or a correct YAML review on the fallback path) |
| GitOps | 5 | ArgoCD Synced/Healthy, OutOfSync → Synced after the tag change, rollback by `git revert` (or a correct written explanation on the fallback path) |
| Reflection + honesty | 5 | clear answers below; limitations and simulated steps stated honestly; no credentials anywhere |

## 6. Reflection (5-10 lines each)

1. What worked on the first attempt? What failed, and how did you diagnose it?
2. Why does the Deployment use exactly **one** replica and the `Recreate` strategy?
3. Why is the image tag `day4-v1`/`day5-v2` and never `latest` in a GitOps workflow?
4. ConfigMap vs Secret: what goes where in this project, and why is the Secret not in Git?
5. Explain in your own words what ArgoCD did when you changed one line in Git.
6. What would you change before running RootCause Copilot for a real company?
