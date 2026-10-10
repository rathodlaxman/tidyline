# Things 3 System Audit

## Role

Act as a senior Things 3 expert, GTD (Getting Things Done) practitioner, productivity systems designer and executive workflow consultant.

Your job is to perform a complete audit of my existing Things 3 system and recommend a better, simpler and more efficient structure.

Do NOT blindly reorganise everything.

Your objective: reduce cognitive load, improve clarity, eliminate unnecessary complexity, and make it immediately obvious what I should work on next.

I have attached my exported Things 3 data as one JSON file. Treat it as the source of truth for my current system.

## About the data

{{DATA_NOTE}}

- `areas`, `projects`, `headings`, `tasks` and `recurring_templates` each carry an `id`. Other items point to them with `{"id": ..., "title": ...}` references.
- Each task has `status` (open, completed or cancelled), `trashed`, and `effective_status`: where the task actually appears in Things (inbox, today, this_evening, upcoming, anytime, someday or closed). Ignore items where `trashed` is true unless I ask about them.
- `start_date` and `deadline` are dates. `recurrence.text` is a readable description of a repeat rule.
- `findings` is a list of automatic health-check results. Each has a `check`, a `severity`, a fixed `message`, and `refs` that point to items by `id`.

## My context

- Who I am and what I do: {{CONTEXT_ROLE}}
- Major ongoing responsibilities and priorities: {{CONTEXT_PRIORITIES}}
- Key dates or transitions that shape the next 6-12 months: {{CONTEXT_DATES}}

My biggest risk is overloading my task manager with too many Areas, Projects, Tasks, Tags and scheduled dates. I want a system that is powerful but simple.

## Objectives

Perform a complete audit of my current Things 3 database. Analyse: Areas, Projects, Headings, Tasks, Inbox, Today, Upcoming, Anytime, Someday, Tags, Deadlines, Start dates, Recurring tasks, and completed or stale items where available.

## Part 1: Current system audit

Describe my current system WITHOUT changing anything.

- **A. Areas.** List every Area with its number of Projects and Tasks.
- **B. Projects.** List Projects under each Area.
- **C. Task volume.** Identify Areas and Projects that appear overloaded.
- **D. Tags.** List all tags and identify useful, redundant, overlapping and eliminable tags.
- **E. Scheduling.** Analyse how I use Today, Upcoming, Anytime, Someday and Deadlines. Identify possible misuse.

## Part 2: Structural problems

Identify problems such as:

- Something that should be an Area but is a Project
- Something that should be a Project but is a Task
- Something that should be a Heading
- Projects that are really just categories
- Tasks that are really projects
- Duplicate, vague or non-actionable tasks (only where the data lets you judge)
- Tasks that are too large or should be broken down
- Projects without a clear outcome or without a next action
- Excessive tags or excessive scheduling
- Tasks that belong in Anytime or Someday
- Tasks that appear obsolete
- Possible missing projects or missing next actions

## Part 3: Redesign

Create your recommended Things 3 architecture. Use the smallest practical number of Areas. For each Area provide: Area, then Projects, then Headings, then Tasks. Do not create complexity just for the sake of organisation.

## Part 4: Migration table

This is extremely important. Create a table with these columns:

| Current Item | Current Location | Recommended Location | Action | Reason |

Possible actions: KEEP, RENAME, MOVE, MERGE, SPLIT, CONVERT TO PROJECT, CONVERT TO TASK, CONVERT TO HEADING, MOVE TO ANYTIME, MOVE TO SOMEDAY, DELETE, REVIEW.

Cover all significant structural changes. Refer to every item by exactly the name given in the data, so I can match it back to my own system.

## Part 5: Task quality audit

{{PART5_BODY}}

## Part 6: GTD classification

For each relevant task, decide whether it belongs in Inbox, Today, Upcoming, Anytime, Someday, Waiting or a Project.

- Inbox: captured but not yet clarified.
- Today: a realistic commitment for today.
- Upcoming: intentionally scheduled for a future date.
- Anytime: something I definitely intend to do but don't yet need to schedule.
- Someday: interesting or desirable but not currently committed.
- Waiting: dependent on another person.

Do NOT schedule everything.

## Part 7: Tag redesign

Recommend a minimal tag system of roughly 5-10 genuinely useful tags. Evaluate each tag by whether it helps answer: "What kind of task can I do right now?" Candidate examples: Computer, Phone, Online, Errand, Deep Work, Quick, Reading, Waiting. Choose only the tags my data justifies.

## Part 8: Daily operating system

Design my daily workflow.

- **Morning:** how to review Today, how many tasks to commit to, how to select priorities.
- **During the day:** how to capture new tasks and avoid constant reorganising.
- **Evening:** how to process unfinished tasks, how to use This Evening, how to prepare tomorrow.

## Part 9: Weekly review

Design a simple 30-45 minute weekly review as a checklist. Include: Inbox, Today, Upcoming, Projects, Anytime, Someday, Waiting, and one check per Area of my life or work. My Areas: {{AREA_LIST}}

## Part 10: Biggest productivity risks

Based on my actual database, identify my top 10 risks. For each, use this format:

**Problem, Evidence, Why it matters, Recommended fix**

Do not give generic productivity advice. Base every risk on my data.

## Part 11: Final recommended system

Provide one clean master structure (Area, Project, Heading, Task), plus:

- Recommended tags
- Recommended recurring tasks
- Recommended weekly review
- Rules for Today
- Rules for Anytime
- Rules for Someday

## Constraints

1. Do not over-engineer the system.
2. Do not create an Area for every topic.
3. Do not turn every collection of tasks into a Project.
4. Do not schedule every task.
5. Do not create excessive tags.
6. Do not blindly preserve my current structure.
7. Do not blindly delete things either.
8. Preserve important information.
9. Clearly distinguish structural problems from personal preference.
10. When uncertain, flag the item for my review rather than making an arbitrary decision.

## Output style

Clear, concise, practical. Tables, decision rules, minimal repetition. No long theoretical GTD lecture. I want a professional audit of my actual Things system followed by a practical redesign.

## Final deliverable

End with a one-page **Things 3 Operating Manual** covering:

1. How I capture
2. How I process Inbox
3. How I use Today
4. How I use This Evening
5. How I use Upcoming
6. How I use Anytime
7. How I use Someday
8. How I create Projects
9. How I write Tasks
10. How I use Tags
11. How I conduct my Weekly Review

The final system should satisfy one objective:

**OPEN THINGS, KNOW WHAT TO DO, DO IT, COMPLETE IT, MOVE ON.**
