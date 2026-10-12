# Getting started with tidyline

This guide is for people who use Things 3 but have never used a command line tool. It takes about 15 minutes. You do not need to know how to program.

**What tidyline is.** A small program that reads a copy of your Things 3 database on your Mac and tells you what is wrong or untidy: to-dos with no project, duplicates, projects with nothing left to do, repeating to-dos it cannot read, and more.

**What it is not.**
- It is **read-only**. It never changes your Things data.
- It works **offline**. It does not send anything anywhere. The only network use is a future, optional feature that you must turn on yourself.
- It is **unofficial**. It is not made by or affiliated with Cultured Code, the makers of Things.

## 1. What you need

- A Mac with Things 3 installed.
- Python 3.10 or later and a tool to install Python programs. The easiest is [uv](https://docs.astral.sh/uv/), which also installs Python for you. Follow uv's own installation page, then come back. pipx also works.

## 2. Install tidyline

Open the Terminal app (Applications > Utilities > Terminal) and type one of these, then press Return:

```
uv tool install tidyline
```

or, if you use pipx:

```
pipx install tidyline
```

Check that it worked:

```
tidyline --version
```

You should see a version number such as 0.2.1. This guide needs 0.2.1 or later.

## 3. Check that tidyline can read your database

```
tidyline doctor
```

`doctor` checks that your Things database exists, that tidyline understands its layout, and that nothing is wrong. It reads a **copy** of the database, so you do not need to quit Things.

If it says something failed, the message tells you what went wrong and what to try next. macOS may also ask whether Terminal may access data from other apps. If it asks, you have to allow it for tidyline to read the database (the exact prompt can differ between macOS versions and has not been tested on all of them).

## 4. Look at your system

```
tidyline report
```

This prints a summary: how many open to-dos you have, how many are in Inbox, Today, This Evening, Upcoming, Anytime and Someday, how many repeating templates, any values tidyline could not read cleanly, and how many findings each health check has. This text summary shows **counts only**, never the titles of your to-dos, so it is safe to paste into a message or a bug report. (The HTML version below is different: it shows your titles.)

```
tidyline check
```

This runs ten health checks. Each check has a heading with its name, severity and number of findings, and the items it found are listed under it, grouped by project or area where that helps. The guide [FIXING_PROBLEMS.md](https://github.com/rathodlaxman/tidyline/blob/main/docs/FIXING_PROBLEMS.md) explains each one and how to fix it in Things.

Unlike the text `report`, the text output of `check` shows the **real titles** of the items, on your own screen only. Do not paste it into a public place. `tidyline check --json` prints ids and fixed messages only, with no titles.

```
tidyline recurrence
```

This lists your repeating to-dos with a plain-English description of each one ("Every 2 weeks on Sun"). Unlike the text `report`, this command shows your real titles, so do not paste its output into a public place.

### See it in your browser

`report` can also write an HTML page that is easier to read, with every health check and the items it found. This needs tidyline 0.3.0 or later.

```
tidyline report --html --out ~/tidyline-out/report.html
open ~/tidyline-out/report.html
```

The first command writes the file. The second opens it in your web browser. The page works offline and loads nothing from the internet.

**This file contains your task titles** and the names of your projects and areas. Keep it private. Do not commit it, attach it to a bug report or share it. tidyline will not overwrite it, so delete it when you have finished reading, before you make a new one:

```
rm ~/tidyline-out/report.html
```

At the end of the page, "Want a deeper review?" shows the commands for step 5 below. tidyline itself does not write recommendations.

## 5. Optional: ask an AI assistant to review your system

Only do this if you want to. tidyline never contacts an AI service. You carry the files across yourself.

1. Make the files:

   ```
   tidyline prompt --anonymise strict --out ~/tidyline-out
   ```

   tidyline creates the folder `~/tidyline-out` for you, readable only by you, if it does not exist. Do not use a folder that is synced or backed up to a cloud service for these files.

   tidyline first shows a **preview** of what will be in the file and what has been left out. Read it. Nothing has been sent anywhere. It then writes two files into the folder: a prompt (the instructions for the assistant) and a payload (your data, with titles replaced by labels like "Task k7f3az").

2. The payload holds **open work only**, plus ready-made counts. Finished and trashed to-dos appear only as numbers.

3. Open a **private chat** (in Claude, an incognito chat) with memory switched off, and also check the assistant's profile and personal-preference settings. Claude's help says incognito chats do not use memory but can still use profile information such as custom styles and personal preferences ([source](https://support.claude.com/en/articles/12260368-use-incognito-chats), read 2026-10-11). Clear or pause those settings if you do not want them to appear in the answer. Other assistants have similar settings; check yours. Then attach the payload file and paste the prompt.

4. Save the assistant's answer into a text file, for example `~/tidyline-out/answer.md`.

5. Put the real titles back:

   ```
   tidyline decode ~/tidyline-out/answer.md --out ~/tidyline-out/answer-readable.md
   ```

   The result contains your real titles. It is personal data. Keep it private.

### How private is it?

- **strict** (recommended) replaces every title and name with a label, removes notes and checklist text, and withholds the raw start, anchor and end dates inside repeat rules. It keeps the structure, dates, counts and the readable schedule text.
- **light** keeps your titles and removes notes. It also removes web addresses, email addresses, money amounts, phone numbers and long digit strings. Use it only if you are comfortable sharing your titles with the assistant.
- Your Things database, tidyline's output files and the decoded answer never leave your Mac unless you send them.

### Check the answer before you act

AI answers vary between assistants and between runs, and they can be wrong. tidyline has only been tried once with each of two assistants. Before you change anything:

- Compare the assistant's counts with `tidyline report`. If the numbers disagree, trust `report`.
- Look for statements about things that are not in your data.
- Back up first (see [FIXING_PROBLEMS.md](https://github.com/rathodlaxman/tidyline/blob/main/docs/FIXING_PROBLEMS.md)). Make changes in small groups.

## 6. Files tidyline writes

- Output files are readable only by you. If the `--out` folder does not exist, tidyline creates the last level of it, also readable only by you, and tells you. It never creates more than one level; if the parent is missing it stops and says so. It does not change a folder that already exists, but warns if other users can read it.
- Do not use a folder that is synced or backed up to a cloud service (iCloud Drive, Dropbox and similar) for these files.
- tidyline will not overwrite an existing file. If it refuses, pick a new name or folder.
- Do not put exports, the HTML report, the text output of `check` or `recurrence`, or decoded answers into any public place. They contain personal data. The text `report` and `check --json` show no titles.

## 7. If something goes wrong

- Run `tidyline doctor` and read the message.
- Run the command again with `--verbose` before the command name, for example `tidyline --verbose doctor`, for more detail.
- If tidyline says it does not recognise your database layout, check your Things version against [COMPATIBILITY.md](https://github.com/rathodlaxman/tidyline/blob/main/docs/COMPATIBILITY.md). tidyline reads parts of the Things database that Cultured Code does not document, and it has been tested on a small number of versions.
- To report a problem, open an issue at https://github.com/rathodlaxman/tidyline/issues. Include the tidyline and Things versions and the message, and **do not include titles or other personal data**.

## Next

- Fix what `check` found: [FIXING_PROBLEMS.md](https://github.com/rathodlaxman/tidyline/blob/main/docs/FIXING_PROBLEMS.md)
- Understand repeat rules: [RECURRENCE.md](https://github.com/rathodlaxman/tidyline/blob/main/docs/RECURRENCE.md)
- See which versions have been tested: [COMPATIBILITY.md](https://github.com/rathodlaxman/tidyline/blob/main/docs/COMPATIBILITY.md)
