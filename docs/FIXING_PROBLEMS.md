# Fixing the problems tidyline finds

tidyline looks at your Things database and tells you what it found. It never changes anything. This guide explains each finding in plain words and shows how to fix it yourself in Things 3 on a Mac.

tidyline is unofficial and is not affiliated with Cultured Code.

## Read this first

**1. Where your titles show up.** `tidyline report` prints counts only, so you can paste it into a chat or a bug report. `tidyline check` prints each finding with the titles of the items it is about, on your own screen, so do not paste its output into a public place. `tidyline check --json` prints fixed messages and ids only, with no titles. Use the titles from `check` to find the items in Things, and the hints under each finding to fix them.

**2. Back up before you change many things.** Things for Mac makes an automatic backup every 24 hours while the app is running (checked). You can undo your last action with Cmd+Z (checked). Restoring a whole backup is a long procedure and has warnings, especially if you use Things Cloud, so read Cultured Code's page before you rely on it: [Restoring from a backup](https://culturedcode.com/things/support/articles/2803595/). Cultured Code's help does not describe a manual backup button (not verified that none exists).

**3. A finding is a question, not an order.** Some findings are warnings (probably a problem) and some are info (a list for you to judge). If you did it on purpose, leave it.

**4. How the steps were checked.** Every step below is marked:

- **[checked]**: the step is written on a Cultured Code help page, read on 2026-10-11. The link is in the sources list at the end.
- **[not verified]**: Cultured Code's help does not describe it, or tidyline's author has not tried it. Use your own judgement and trust what you see on screen. If the app looks different from this guide, the app is right.

This guide was written against Things 3.24.1. Menus change between versions.

## The ten checks

Run `tidyline check` to see which ones apply to you. To look at one check, run `tidyline check --only NAME`, where NAME is the check name shown in the list below (see `tidyline check --help` if the options have changed).

### 1. open_in_trashed_project (warning)

**What it means.** A project is in the Trash, but some to-dos inside it are still open. `tidyline report` also shows how many there are.

**Why it matters.** Those to-dos may not show up in any list, so you may forget them. Every other tidyline check ignores them for this reason.

**How to fix.**
1. Open the Trash in the sidebar. [not verified: exactly how open to-dos appear inside a trashed project]
2. Drag the to-dos you still want out of the Trash and onto a project or list in the sidebar. Dragging items out of the Trash is supported [checked, release notes 3.15.3]. You can also move a to-do with Shift-Cmd-M [checked].
3. If you want the whole project back, drag the project out of the Trash [checked, same release note].
4. Emptying the Trash is permanent. Cultured Code's help does not describe emptying the Trash [not verified], so do not do it until you have moved out what you want.

**Confirm.** Run `tidyline check` again. The count should go down.

**When to ignore.** If you deleted the project because the whole thing is finished or dead, you can leave its leftover to-dos in the Trash.

### 2. unfiled_open (warning)

**What it means.** An open to-do is in no project and no area. tidyline does not count Inbox items here, because the Inbox is meant for things you have not sorted yet.

**Why it matters.** To-dos with no home are hard to review. They appear in your lists but belong to nothing.

**How to fix.**
1. Select the to-do and press Shift-Cmd-M, then choose the project or area [checked]. You can type part of a name to search [checked]. You can select several to-dos and move them together [checked].
2. To make a new project in the same step, type its name and choose "+ New Project" [checked].

**Finding them.** Use the search (Cmd+F) [checked]. [not verified: a view in Things that lists only items with no project or area]

**Confirm.** `tidyline check --only unfiled_open`.

**When to ignore.** A to-do you deliberately keep loose, such as a one-off errand.

### 3. title_hygiene (warning)

**What it means.** A title has a stray "·" at the start or end, extra spaces at the start or end, or two spaces in a row. If you used `--pattern`, it can also mean a title matched your own pattern.

**Why it matters.** It is cosmetic, but it causes false duplicates and makes searching less reliable.

**How to fix.** Open the to-do and edit its title. To find the ones with a stray "·", search for "·" with Cmd+F [checked]. Spaces are invisible, so you may need to click into the title to see them.

**Confirm.** `tidyline check --only title_hygiene`.

**When to ignore.** Always safe to ignore if you do not mind.

### 4. possible_duplicates (warning)

**What it means.** Two or more open to-dos have the same title once capital letters and punctuation are ignored (apostrophes are dropped, and other punctuation counts as a space). Accents still count, so "cafe" and "café" are different. Copies of one repeating to-do are not counted.

**Why it matters.** The same task may be in two places, so you do it twice or forget one copy.

**How to fix.**
1. Search for the title with Cmd+F [checked].
2. Decide which copy to keep. Look at each copy's project, notes, dates and tags before you delete one. Cultured Code's help does not describe merging to-dos [not verified], so copy any notes you need across by hand.
3. Delete the extra copy [not verified: the exact menu or key]. If you delete the wrong one, press Cmd+Z straight away [checked].

**Confirm.** `tidyline check --only possible_duplicates`.

**When to ignore.** Two items that look the same but belong in different projects (for example "Call bank" for two accounts). Consider making the titles more specific.

### 5. dated_in_someday_project (warning)

**What it means.** A to-do has a start date, but its project is set to Someday. tidyline's rule is that everything inside a Someday project stays parked, so the date will never bring the to-do to Today.

**Why it matters.** You may expect a reminder that never comes.

**Source of this rule.** Cultured Code's help does not describe this case. tidyline's rule comes from watching how the app behaved (see docs/DESIGN.md, section 7.1). If you see the to-do appear in Today, tell the maintainer without sharing any titles.

**How to fix.** Choose one of these:
- Take the date off the to-do: select it, press Cmd+S and click Clear [checked]. It then goes to Anytime inside the project.
- Make the project active again. [not verified: the exact step for moving a project out of Someday. The project's own "When" setting (Cmd+S) is the likely place.]
- Move the to-do out of the project with Shift-Cmd-M [checked].

**Confirm.** `tidyline check --only dated_in_someday_project`.

**When to ignore.** If you want the project parked and the date is a leftover, clear the date and move on.

### 6. active_project_no_open_tasks (warning)

**What it means.** A project that is not in Someday has no open to-dos and no repeating to-do in it.

**Why it matters.** An active project with no next action is a stalled project. It sits in your lists but nothing moves it forward.

**How to fix.** Choose one:
- Add the next step as a to-do. Cultured Code suggests planning only the next one to three steps of a project [checked].
- If the project is finished, complete it: select it and press Cmd+K [checked].
- If it is "maybe later", set the project to Someday. [not verified: the exact step]

**Confirm.** `tidyline check --only active_project_no_open_tasks`.

**When to ignore.** A project you are waiting on, if you track the waiting some other way.

### 7. recurrence_not_recognised (warning)

**What it means.** tidyline found a repeating to-do whose rule it cannot read, so it will not guess. The repeat rules are stored in a part of the Things database that Cultured Code does not document, so this check exists to be honest about that.

**Why it matters.** Other tidyline output about that to-do's schedule may be missing.

**How to fix.** There is nothing to fix in Things. To see the rule as Things shows it:
1. Search for "repeating" with Cmd+F and choose Repeating [checked].
2. Double-click the repeating to-do to open it [checked].
3. Click Repeat > Change to see the schedule [checked].

If tidyline cannot read a rule that Things shows normally, please report it at https://github.com/rathodlaxman/tidyline/issues and describe the schedule in words ("every 2 weeks on Sunday"). Do not paste titles.

**When to ignore.** Safe to ignore if the repeat works in Things.

### 8. leftover_templates (info)

**What it means.** A repeating template is still live, but its project is in the Trash or has gone. "Template" means the hidden master copy that creates the repeats.

**Why it matters.** It may keep creating to-dos, or it may do nothing. Either way it is clutter.

**How to fix.**
1. Find it in the Repeating list (Cmd+F, type "repeating") [checked]. [not verified: whether templates inside trashed projects appear there]
2. Open it. Click Repeat > Stop to turn it into a plain to-do [checked], or Repeat > Pause to keep it but stop new copies [checked].
3. Then delete the to-do, or move it into a live project with Shift-Cmd-M [checked].

**Confirm.** `tidyline check --only leftover_templates`.

**When to ignore.** If you cannot find it, leave it. It is harmless.

### 9. someday_in_active_project (info)

**What it means.** A to-do is set to Someday inside a project that is active.

**Why it matters.** It is not a problem by itself. Parked steps inside a live project are common. A large number can mean the project holds too many "maybe" items.

**How to fix.** For each one, decide: do it soon, keep it parked, or delete it. To bring one back, select it, press Cmd+S and click Clear, which puts it in Anytime [checked]. Cultured Code suggests reviewing Someday every couple of months [checked].

**When to ignore.** Often. This list is for you to judge.

### 10. outside_heading (info)

**What it means.** A project that uses headings has some open to-dos that sit above or outside every heading.

**Why it matters.** The project looks half-organised, and loose to-dos at the top are easy to overlook.

**How to fix.**
1. To put to-dos under an existing heading, select them, press Shift-Cmd-M, and type the heading's name [checked].
2. To make a new heading, open the project and press Shift-Cmd-N [checked]. To group selected to-dos under a new heading, hold Option and choose File > New Heading with Selection [checked].

**Confirm.** `tidyline check --only outside_heading`.

**When to ignore.** If the loose to-dos are your "next actions" and you like them at the top.

## Things an AI assistant may tell you to do

If you used `tidyline prompt`, the assistant's answer will use these phrases. Check the answer against `tidyline report` before you act.

| The assistant says | In Things 3 on a Mac |
|---|---|
| "Move it to a project or area" | Select it, press Shift-Cmd-M, pick the destination [checked] |
| "Take it out of its project" | Select the to-do and choose Items > Remove from Project/Area [checked] |
| "Turn this to-do into a project" | Open the ••• menu of the to-do and choose Convert to Project [checked, from release notes 3.15.8, 3.15.9 and 3.17; this command is off for repeating to-dos]. Each checklist item becomes its own to-do [checked] |
| "Add a heading" | Open the project, press Shift-Cmd-N [checked] |
| "Put these under a heading" | Select them, press Shift-Cmd-M, type the heading name [checked] |
| "Schedule it" or "give it a start date" | Select it, press Cmd+S, pick a day [checked] |
| "Move it to Someday" | Cmd+S, then choose Someday in the date picker [checked] |
| "Move it to Anytime" | Cmd+S, then click Clear [checked] |
| "Put it in This Evening" | Cmd+S, then choose This Evening [checked] |
| "Add a deadline" | Shift-Cmd-D [checked], or click the deadline button in the to-do [checked]. To remove it, click the deadline and choose Clear [checked] |
| "Add or change a tag" | Select the to-do(s) and press Shift-Cmd-T [checked] |
| "Rename or delete a tag" | Window > Tags [checked] |
| "Merge two tags" | Cultured Code's help does not describe merging [not verified]. You can nest one tag under another in the Tags window [checked] |
| "Change or stop a repeating to-do" | Repeating list, double-click, then Repeat > Change, Pause, Resume or Stop [checked] |
| "Break this big task down" | For a small goal, use a checklist [checked]. For a bigger one, make a project and add to-dos and headings [checked] |
| "Review Someday regularly" | Cultured Code suggests every couple of months [checked] |
| "Delete it" | Select it and delete [not verified: exact menu or key]. Press Cmd+Z straight after if you change your mind [checked] |

Some advice from assistants is about taste, not correctness: how many areas to have, which tags to keep, whether to schedule things. Treat it as a suggestion. Ask whether the assistant is pointing at a real problem in your data or just a habit it likes.

## Sources

Cultured Code's own help pages and blog, read on 2026-10-11:

- [Moving Items in Things](https://culturedcode.com/things/support/articles/9651894/)
- [Using Headings in Projects](https://culturedcode.com/things/support/articles/2803577/)
- [Restoring From a Backup](https://culturedcode.com/things/support/articles/2803595/)
- [Using Repeating To-Dos](https://culturedcode.com/things/support/articles/2803564/)
- [Scheduling To-Dos in Things](https://culturedcode.com/things/support/articles/2803579/)
- [Using Tags](https://culturedcode.com/things/support/articles/2803581/)
- [Keyboard Shortcuts for Mac](https://culturedcode.com/things/support/articles/2785159/)
- [An In-Depth Look at Today, Upcoming, Anytime, and Someday](https://culturedcode.com/things/support/articles/4001304/)
- [Why Some To-Dos Get Stuck and How to Get Them Moving Again](https://culturedcode.com/things/support/articles/8491676/)
- [Frequently Asked Questions](https://culturedcode.com/things/support/articles/2967034/) (Trash and Cmd+Z)
- [Mac Release Notes](https://culturedcode.com/things/support/articles/1100684/) (Convert to Project; dragging items out of the Trash)
- [Repeating To-Dos, Refined](https://culturedcode.com/things/blog/2026/08/repeating-to-dos-refined/) (Things 3.23)
