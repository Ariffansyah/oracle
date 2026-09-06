# Project Brief: Oracle Reviewer 3B

**To:** Agent / Development Team
**Project:** Oracle Reviewer 3B
**Goal:** Build a fully local, private AI code review companion powered by a fine-tuned 3B parameter LLM, featuring a Tkinter-based desktop interface.

## 1. Core Architecture & UI
* **Completely Local & Private:** No web server, cloud APIs, or GitHub integrations. The application must run entirely offline.
* **UI Framework:** Strictly built with **Tkinter** for a standalone desktop application. It must display the file list on one side and the diffs/AI suggestions on the other with basic "Apply" and "Discard" actions.
* **Model:** A Supervised Fine-Tuned (SFT) 3B LLM, running locally (e.g., via Ollama or llama.cpp).

## 2. Review Processing Rules
* **Per-File Incremental Review:** The system must evaluate commits file-by-file. It should never review all files in a single commit at once to prevent context overflow and hallucinated diffs.
* **Risk-Adaptive Output Engine:** The model must evaluate the logic of the diff and adapt its response based on the risk level:
  
  * **High-Risk Bugs (Detailed Explanation):** 
    * *Trigger:* If the model tests/calculates a high probability of a bug (e.g., typos in variables, type mismatches, null references, syntax errors).
    * *Action:* Thoroughly explain *why* the code will fail or throw an error, followed by the suggested fix.
  
  * **Behavior / Style Changes (Direct Statement):** 
    * *Trigger:* Simple structural changes, stylistic updates, or behavior tweaks (e.g., changing a kill reward from `+10` to `+20`, or renaming a variable).
    * *Action:* State the change directly and concisely without over-explaining, followed by the suggested patch.

## 3. Required Output Examples

### High-Risk Bug Example
**Oracle AI** `[High Risk]`
`dealNewCards` updates score using `newState.scor`, which is a typo and will fail type-checking or throw a runtime error. It also changes the deal penalty from `-1` to `-2`, which is inconsistent with the game rules used elsewhere.

```diff
- score: newState.scor - 2 // Small penalty for dealing
+ score: newState.score - 1 // Small penalty for dealing
```

### Low-Risk / Behavior Change Example
**Oracle AI** `[Behavior Change / Refactor]`
The correct property is `req.params.id`, not `req.param("id")`. The kill reward modifier was also updated from 10 to 20.

```diff
- let id = req.param("id");
- let reward = kills * 10;
+ let id = req.params.id;
+ let reward = kills * 20;
```
