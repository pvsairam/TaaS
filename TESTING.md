# How to test Quartermaster

This guide is for someone using Quartermaster for the first time. Follow the parts in order.
Each step says what to do and what you should see. If you see something else, write it down
(see "Reporting a problem" at the end).

Commands are for Windows PowerShell. Type them in the `TaaS` folder.

## Part 1. What you need

- A Windows laptop that can open your Oracle Fusion test pod in a browser.
- Python 3.11 or newer. Check with `python --version`.
- Git. Check with `git --version`.
- The pod address, a test user name and its password. Use a test pod only, never production.

## The easy way: no terminal

1. Get the `TaaS` folder onto the laptop once (the `git clone` lines below, or a copy of the
   folder).
2. Open the `TaaS` folder and double-click **Start Quartermaster**.

You should see: a black window. The first time it says it is installing (a few minutes, only
once), then it puts a **Quartermaster** icon on the desktop. Your browser opens Quartermaster. If
nothing is set up yet, the setup guide opens (see 6.1).

- From then on, double-click the **Quartermaster** icon on the desktop to start it.
- Keep the black window open while you use Quartermaster. Close it to stop.
- Double-clicking the icon again while it runs just opens the browser.
- To get the latest version: close the black window, then double-click **Update Quartermaster**
  in the `TaaS` folder.

The parts below are the same steps done by hand in a terminal, for testers and developers.

## Part 2. One-time setup

Do this once on a new laptop.

```powershell
git clone https://github.com/pvsairam/TaaS.git
cd TaaS
git checkout claude/awesome-bardeen-r668wx
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,browser]"
python -m playwright install chromium
```

You should see: no red error lines. The last command downloads a browser and can take a few minutes.

## Part 3. Every time you open a new terminal

1. Go to the folder and switch on the Python environment:

   ```powershell
   cd TaaS
   .venv\Scripts\activate
   ```

   You should see `(.venv)` at the start of the line.

2. Get the latest version:

   ```powershell
   git pull
   ```

3. Nothing else is needed: the pod and its users are set up in the web app (Part 6.1). If you
   used the terminal variables before (QM_FUSION_URL, QM_FUSION_USER, QM_FUSION_PASSWORD), the
   first start of `qm serve` copies that pod into the app as "My first client", so you can stop
   setting them. The command line test in Part 5 still needs them.

## Part 4. Automatic checks (no pod needed)

```powershell
python -m pytest -q
```

You should see: a line like `NNN passed`, with no `failed`. Some tests may say `skipped`; that is fine.

If anything says `failed`, stop here and report it.

## Part 5. Sign in to the pod from the terminal

```powershell
qm run examples/smoke/login.yaml --headed
```

You should see: a browser opens, signs in to the pod and closes. The terminal prints `PASSED`
(or `HEALED`) for `smoke.login` and `1/1 passed`.

If it says it cannot sign in, check the three values from Part 3.

## Part 6. Open the web app

```powershell
qm serve
```

You should see: the terminal says `Quartermaster is running at http://127.0.0.1:8765` and your
browser opens that page. The first time, it also says `Created my_tests`: your own tests are kept
in the `my_tests` folder, which starts with copies of the example tests. Do not start it with
`--tests examples/tests`: your tests would then be saved among the examples, and the automatic
checks in Part 4 would fail. Keep this terminal open while you test. Press Ctrl+C in it to stop.

The left side has the menu: Overview, Runs, Tests, Release impact, Needs attention,
Record a test, Settings.

### 6.1 Settings: clients and environments

The very first time (nothing set up yet, and no pod set in the terminal), Quartermaster opens the
**Set up Quartermaster** guide by itself: four steps (Client, Pod, Sign-in, Check). Fill them in and
click **Save and check**. If the pod does not answer, check the address or your VPN and click
**Check again**. To add another client the same way later, open Settings and click **Setup guide**.

Settings has four tabs: **Clients & environments**, **Evidence**, **AI assistant** and **General**
(folders, theme, keyboard shortcuts).

1. Click **Settings**. On the left, **In use now** shows the pod runs use, and
   **Clients and environments** lists your clients and their pods.
2. If it is empty, click **Add a client**, type the client's name (for example `Acme Corp`) and
   click **Save**. The New environment panel opens by itself.
3. Fill in: Name (`DEV2`), Oracle release (`26C`), Pod address (copy it from the browser when the
   pod's sign-in page is open), Kind (Development, Test or Stage / UAT), Sign-in (User name and
   password). Under **Test users**, type the default user and its password. If a test switches
   user (for example a Line Manager approves), click **Add persona** and fill in that user too.
4. Click **Test connection**, then **Save**.

You should see: the environment in the list with "In use", and "Signs in as <user>". The password
is never shown again; the field says "Saved. Type to change". It is saved encrypted by Windows for
your Windows user only.

5. Add a second client the same way (**Add client** at the top of the card). To switch, click the
   environment box at the bottom-left of the menu and pick it under **Switch to**, or click
   **Use** next to it in Settings. Runs, recordings and Prepare then go to that pod.
   Each client is kept apart: its own tests, manual scripts, evidence, runs, schedules, Needs
   attention and audit log. Switch to the second client: **Tests** shows only its tests (a new
   client starts with copies of the example tests), **Runs** shows none of the first client's
   runs. Switch back: everything of the first client is still there. The first client keeps the
   folders you had before (`my_tests`, `evidence`); every other client's files are in
   `clients/<name>-<code>/`. Schedules of every client run even when another client is in use.
6. Try adding a production pod (an address without dev, test, stage or uat, such as
   `https://acme.fa.us6.oraclecloud.com`): Quartermaster refuses it. If a real test pod has no such
   word in its address, tick **This is a test pod, not production** and save again.
7. In the **Evidence** tab, choose Screenshots and Video and whether to show the browser.
   Each change is saved at once. Every run you start afterwards uses them.
8. **Highlight clicks** is on by default. Start a run with **Show the browser while it runs** on:
   before each click a red box and a small red dot appear on the item for a moment (also in the
   video), and the screenshots have a red box round the item each step used. Turn it off and run
   again: no red marks anywhere.

### 6.2 Run one test

1. Click **New run** (top right).
2. Choose **One test**, pick "Search for a worker in Person Management and open their record".
3. Leave the other options as they are. Click **Start run**.

You should see: the run page with live progress ("Executing step 2 of ...") and then a result.
When it ends, each step has a screenshot. There is a link to the Word evidence document and a
summary document. Open both. They should open in Word and show the steps and pictures.

### 6.3 Run all tests

1. Click **New run**, choose **All tests**, click **Start run**.

You should see: 4 tests run one after another. The result shows how many passed.

### 6.4 Runs

1. Click **Runs**.

You should see: every run so far, newest first, with result, release, who ran it and how long it took.
Click one to open it again.

### 6.5 Tests

1. Click **Tests**.
2. Type `worker` in the search box. Then clear it.
3. Click **Columns** and tick one more column, for example Owner.
4. Click a test name.

You should see: the search filters the list. The extra column stays after you reload the page.
The test page shows its steps in plain words, its test data, its run history and the file.

### 6.6 Release impact

This page answers: "Oracle is updating the pod. Which of our tests should we run, and what is not
tested at all?"

1. Click **Release impact**. The example release `26D` opens.
2. Look at the four cards at the top: features in the release, tests at risk, suggested run,
   features with no test.
3. In the **Tests to run** tab, click **Covers ...** on a row to see why that test was picked.
4. Type `3` in **Time limit (minutes)** and press Enter. The suggested tests change to what fits
   in 3 minutes.
5. Click the **Features** tab, then **No test**. This lists features that no test covers.
6. Click **Import feature list**. Choose the file
   `examples\releases\26C_sample_features.csv`. Type `26C` as the Oracle release if it is empty.
7. Read the preview: how many features it found and which columns it used. Click **Save feature list**.
8. The page now shows release 26C. Click the box in the table header until every test is unticked,
   then tick two tests.
9. Click **Run 2 tests**.

You should see: the run page named "Release 26C impact · 2 tests", and only those 2 tests run.
In **Runs**, the run has the same name.

To try a real Oracle file: download the feature listing spreadsheet for an update from Oracle
Cloud Readiness and import it the same way. The spreadsheet must have a Feature column. Product
and Product Family columns make the matching better.

### 6.7 Manual test scripts: import and run

Your Excel test scripts can be added once and run every quarter. The workbooks themselves are
only read; they are not changed.

**Import**

1. Click **Tests**, then **Import manual scripts**.
2. Choose one or more `.xlsx` files. You can select all of them at once.
3. They are saved straight away and the list of scenarios opens. They stay in Quartermaster
   (also after the next quarterly release) until you remove them.
4. Only if Quartermaster cannot tell a workbook's module and product from its file name, the
   window stays open: type them and click **Save**.

**Run a scenario the first time: by hand**

5. On **My Compensation**, click **Run by hand**. A browser opens, already signed in, and
   Quartermaster shows the scenario's steps.
6. Do step 1 in that browser. Then click **Pass** on step 1 in Quartermaster (or **Fail**, type
   what went wrong, and click **Mark failed**). Quartermaster takes a picture of the screen.
7. Do the same for every step. On the last page, click **Add check** and then click a value that
   proves the page is right (for example "Current Salary").
8. Click **Finish**.

You should see: "Every step passed" (or "At least one step failed"), a button for the Word
evidence document, and **Open the run**. The run is in **Runs** as "By hand: My Compensation".

**Run it again: by itself**

9. Go back to **Tests**, **Manual scenarios**. The button on My Compensation now says **Run**.
10. Click **Run**.

You should see: the run page, named "Automatic: My Compensation". Quartermaster plays your
clicks from step 6 and 7 without you, and makes a new evidence document.

**Run** uses the evidence choices in **Settings**, **Evidence**: Screenshots, Video, and Show the
browser while it runs. They are the same choices as in **New run**; changing either changes both.

To do a scenario by hand again (for example after Oracle changed the screen), open it and click
**Do it by hand**. Only run scenarios by hand that are safe to repeat on the test pod: whatever
you click, including Save or Submit, is played again every time.

**Let an AI prepare a scenario instead (optional)**

This needs an AI provider, set once (see "Choosing an AI" below).

11. On **Employment Info**, click **Prepare**. A browser opens, already signed in. The AI reads
    each written step, clicks on the pod by itself, and takes a picture when a step is done.
    Quartermaster shows which step it is on.
12. When it has finished, click **See what the AI did** and compare each picture with its step.
13. If every picture is right, click **Approve**. From then on **Run** plays it by itself.
    If a picture is wrong, click **Do it by hand** instead.

When the script lists fields to check (for example "Current Salary (Salary, Annual Salary)"), the
AI opens a closed section and checks those fields. If the page does not show them, for example
"There's nothing here so far" because the test user has no salary, it stops and says so instead of
passing: use a test user who has that data, or do it by hand.

You should see: before you approve, the button on the scenario says **Review**, and **Run** is
refused. If the AI cannot do a step (for example the script does not give a value to type, or the
step would press Save or Submit), it stops, says why, and nothing is saved to run: do that scenario
by hand.
**What the AI answered** opens the AI's diary: for every step, what was on the screen, what the AI
chose and what did not work. Send it when you report a problem with Prepare. It is also kept in the
run's folder in `evidence\` as `ai-diary.txt`.

**The evidence document of a scenario that plays by itself**

When **Run** plays a scenario, its Word document follows the steps of your script (Login, Me,
Personal Information, Select My Compensation), each with the actions done for it and their
pictures. A step without its own action says why, for example "Quartermaster signed in before the
test started" or "done as part of step 3 (Open Me > Personal Information)". A click has two
pictures: just before it, with what it clicks boxed in red, and after it. Scenarios saved before
this change keep the old layout until you prepare them again or do them by hand again.

**Check what a scenario does, and prepare it again**

- The written steps: in **Manual scenarios**, click the scenario's name. The panel lists each test
  case with its steps and expected results.
- What Run plays: open one of its runs and click **Open test**. It lists the saved actions, for
  example "Open Me > Personal Information", "Click My Compensation" and "Check My Compensation is
  shown". Login is not listed: Quartermaster signs in before every run. A step that only opens a
  page, like "Me", becomes part of the Navigator action.
- If the saved actions are wrong or incomplete, click the scenario's name, then **Prepare again**
  (or **Do it by hand**). The new version waits in **To review** until you approve it; if the AI
  stops, the current version stays.

**Scenarios that submit a scheduled process**

Many payroll and finance scripts submit a process (an ESS job) and then wait for it. While doing
such a scenario by hand (or while recording a test), submit the process in the browser, then click
**Wait for process**. When the test plays, Quartermaster reads the process number from Oracle's
confirmation ("Process 1234567 was submitted"), asks the pod for its status every 15 seconds, and
the step passes only when the process ends with **Succeeded** (it waits up to 30 minutes). When the
AI prepares a scenario, it adds this step itself when a step says to wait for the process. The
status comes from Oracle's ERP integration service, so the test user needs access to it; if not,
the step says so.

**Fill in test data the script does not give**

When a scenario shows **Values not written** or **Test data missing**, click its name. Each step
that needs a value has a box (**TEST DATA NEEDED**). Type the value, for example "Start Date:
01/10/2026; Absence Type: Vacation", and click **Save test data**. The badge goes away, Prepare all
includes the scenario, and the AI and the tester see the value as part of the step. The workbook is
not changed; the values are kept in `.qm`. Never type a password there: do steps that need a
sign-in by hand.

**Prepare many at once (optional)**

14. In **Manual scenarios**, click **Prepare all (N)**. N is the number of scenarios that do not
    play by themselves yet, are not waiting for review, and that the AI can finish: scenarios
    marked **Test data missing**, **Values not written** (a step says "Enter required data" or
    "enter the date" without the value) or **No steps** are left out, because the AI never makes
    values up and would stop there. Do those by hand, or write the values in the workbook and
    import it again. Click OK.
15. The **To review** page opens. It shows each scenario: waiting, preparing now, ready to review,
    or stopped (with the reason). You do not need to watch; **Watch the AI** shows the browser
    steps, and **Stop** stops after the scenario being prepared now. While it runs, Prepare and
    Run by hand wait, because the AI uses the browser.
16. When it has finished, every prepared scenario is listed with the picture of each step. Click a
    picture to see it full size. Tick the scenarios where every picture is right (or **Select all**
    and untick the wrong ones), then click **Approve selected**.

You should see: the approved scenarios now say **Run** in Manual scenarios. Stopped ones still say
**Prepare** and **By hand**. Clicking **Prepare all** again tries the stopped ones again. For a
scenario whose pictures are wrong, click **Do it by hand** in To review.

**Choosing an AI**

1. In **Settings**, **AI assistant**, choose the **Provider** and type the **Model** name your
   account offers (for example the model id shown in your OpenAI or OpenRouter account).
2. Paste your key in **API key** and click **Save**. You should see "Ready: ... Key saved (hidden)".
3. Click **Test the AI**. You should see "... answered in ... ms".

The key is kept in memory only: it is never written to a file and never shown again, so paste it
again after you restart `qm serve`. To keep it across restarts, set it on the computer instead,
like the pod password, before starting: `$env:OPENAI_API_KEY="your key"` (the variable name for
each provider is under **Advanced**). Ollama on your own computer needs no key.

If Anthropic answers "This API key is not scoped to a workspace": open the Anthropic Console,
go to Workspaces and copy the workspace ID (it starts with `wrkspc_`). In Settings, open
**Advanced**, paste it in **Workspace ID**, click **Save**, then **Test the AI** again. Or make a
new key inside a workspace in the Console; then the ID is not needed.

Any provider that offers an OpenAI-compatible service works: choose **Other** and enter its
address. What is sent to the AI: the written steps and the names of the buttons, links and
headings on the pod screen; e-mail addresses and long numbers are hidden first. Never typed
values, never the password. The key is never stored by Quartermaster.

**Other things to check**

- The **Result** column shows Quartermaster's own last result. "Workbook: Pass" in Notes only
  repeats what someone typed in the workbook's Pass / Fail column.
- Scenarios with `<>` in their steps are marked "Test data missing".
- In **Release impact**, the **Manual scenarios** tab lists the scenarios that cover a feature
  of the release. In the **Features** tab, a feature only a manual script covers is "Manual only".
- To remove a workbook: **Imported files**, then **Remove**. To update one, import it again.

#### Type a new scenario (no Excel needed)

1. Click **Tests**, then **Manual scenarios**, then **New scenario**.
2. Name: `Update my home address`. Module: `HCM`. Product: `Global Human Resources`.
3. In the first step box, paste these four lines at once:

   ```
   1. Click Me
   2. Click Personal Information
   3. Enter 10 Main Street in Address Line 1
   4. Click Cancel
   ```

You should see: four steps, one per line, without the numbers.

4. Click **Save**. The scenario opens, marked "Typed in Quartermaster". It is in the list like an
   imported one: **Run by hand** or **Prepare** work the same.
5. Click **Change**, edit a step, and **Save**. Or **Delete** to remove it (past runs stay).

### 6.8 Needs attention

1. Click **Needs attention**.

You should see: failed runs grouped by kind (for example "Item not found"), with the failed step,
what was expected, what was found and a screenshot. If nothing failed it says all clear.

To clear an item, click **Dismiss** on it, or **Dismiss all shown** at the top. A dismissed failure
comes back only if the test fails again on a later run.

Each failed test also says its **Likely cause**, worked out from its history: passed on an
earlier release and fails on this one (probably the Oracle update), passed before on this same
release (the data or the pod changed), or never passed (the test or its data). When the update is
the likely cause there is a **Draft SR** button: it opens the text of an Oracle service request
(steps to reproduce, expected and actual result, releases, pod). Click **Copy** and paste it into
My Oracle Support. Quartermaster never sends it.

To see Draft SR, a test must have passed on one release and failed on the next: run it with the
release set to, say, `26B` in Settings, then change the release and run it again.

### 6.9 Record a test

1. Click **Record a test**.
2. Fill in Test name, Module (for example `HCM`) and Product (for example `Global Human Resources`).
3. Click **Start recording**. A browser opens, already signed in.
4. In that browser, open a page and click through a short, safe flow. Only look at data; do not
   save or submit anything on the pod.
5. Back in Quartermaster, try **Pause** and **Resume**, **Add note**, and **Add check** (then click
   a value on the pod page).
6. Click **Finish and save**.

You should see: each click appears as a step while you record. After saving, the new test is
listed under **Tests** and you can run it.

### 6.10 Schedules (tests that run by themselves)

1. Click **Schedules**, then **New schedule**.
2. Name: `Nightly check`. What to test: one short test. Days: today only. Time: two minutes from
   now on this computer's clock. Keep **On** ticked. Click **Save**.

You should see: the schedule in the list, with "Next run" at the time you chose. Keep `qm serve`
running. Within a minute of that time a run labelled "Scheduled: Nightly check" starts under
**Runs**, and "Last run" on the Schedules page links to it.

3. Click **Run now** on the schedule. It starts the same run straight away.
4. Click the schedule, then **Delete** to remove it. Its runs stay in Runs.

Note: schedules only start while `qm serve` is running. A time missed while it was stopped
starts only if Quartermaster is back within the hour.

### 6.11 Certification pack for a release

Do this after some tests have run with the Oracle release set in Settings (6.1).

1. Click **Overview**. In the release readiness card, click **Certification pack**.
2. A zip downloads, named like `certification_26C.zip`. Unzip it.

You should see: `Certification 26C.docx` and an `evidence` folder with one Word document per
test (its latest run on that release). Open the certification document. It shows the result,
counts by module, every test with its result and evidence file, what failed with a picture,
tests not yet run on the release, and a sign-off table. In **Release comparison** (shown once
tests ran on two releases), the download icon on each row gets the pack for that release.

### 6.12 Audit log

1. Click **Audit log** (under System).

You should see: what you changed in this test session, newest first, with who and when: the run
you started, the schedule you added, settings, test data saved (only which steps, never the
values), approvals. Type a word in the search box to filter. Click **Download CSV** for the whole
log in a file Excel opens. "Who" is the user signed in to this computer, or the tester's name for
a run by hand; scheduled runs show "Schedule".

### 6.13 Search and shortcuts

- Press **Ctrl+K**. Type `release impact`. Press Enter. It opens Release impact.
- Press **N**. The New run panel opens. Press Esc to close it.
- Click the moon or sun icon at the top. The page switches between dark and light.

### 6.14 Cleanup after a test

This test only reads from the pod (GET), so it is safe. It shows that cleanup steps run, and that
they are skipped when there is nothing to clean up. It needs a pod where Locations can be read by
the REST service (the same one used by Create Location).

1. Copy the demo files into your tests folder (they only read from the pod):

   ```powershell
   Copy-Item examples\demos\*.yaml my_tests\
   ```

   Open **Tests** (press F5 if it was already open). You should see three new tests whose names say
   "demo": Cleanup demo, Retry demo and Suggestion demo.

2. In **Tests**, click **Cleanup demo (reads only)**, then **Run this test**.

You should see: the run passes. Under the test's name a blue box says **Test data cleaned up**
("1 cleanup step done after the test"). Open the Word document: near the end there is a
**Cleanup of test data** table with the step marked Passed.

3. Open the file `my_tests\cleanup_demo.yaml` in Notepad (the page only shows a test, it has no edit button) and change `locationsV2?limit=1` to `locationsV9?limit=1`. Run it again.

You should see: the run fails at step 1, and the blue box says **Nothing to clean up**: the test
never saved a location, so the cleanup step was skipped instead of calling an address with a blank
in it. The Word document shows the cleanup step as "Nothing to clean".

4. Save the file. Put `locationsV2?limit=1` back. Now change the cleanup line (in Notepad too) to `value: DELETE /hcmRestApi/resources/11.13.18.05/locationsV2/300`.

You should see: the test is unreadable (see **Needs attention**, "Unreadable files") and says a cleanup
DELETE must use a value the test saved, such as `${location_id}`. Put the line back as it was,
or delete the demo file when you are done.

5. To see a cleanup that fails, in Notepad change the cleanup line (the last `value:` line) of `my_tests\cleanup_demo.yaml` to
   `value: GET /hcmRestApi/resources/11.13.18.05/locationsV2/1` (a location that does not exist), and run the demo.

You should see: the test still **passes**. Click **Needs attention**: a card **Cleanup did not finish** says
"Records from this test may still be on the pod" and lists "Cleanup step 1 (...)" with the pod's answer. The
Overview card says "1 cleanup not finished". **Dismiss** hides it until the next run of that test has a failed cleanup
again. Put the cleanup line back when you are done.

### 6.15 Backup and restore

1. Click **Settings**, then the **General** tab. Find **Backup and restore**.
2. Click **Download a backup**.

You should see: a file named `quartermaster-backup-<date>-<time>.zip` downloads. Open it (it is a
normal zip): there are folders `tests` and `data`, and a file `backup.json`. There is no
`vault.key` and no `evidence` folder (you did not tick the evidence box).

3. Make a change you can recognise: in the `my_tests` folder, delete one of your test files (or open
   **Tests** and note how many there are).
4. Back in **Backup and restore**, click **Restore from a backup**, choose the zip from step 2 and
   click OK in the question.

You should see: a yellow box, **A restore is waiting**. Nothing has changed yet. (Click **Cancel the
restore** to try that: the box goes away.)

5. Choose the zip again to bring the box back. Close the black window, then start Quartermaster
   again (double-click the desktop icon).

You should see: in the black window, "Restored the backup you chose." The test you deleted is
back, and the yellow box is gone. Under **Backup and restore**, "Copies made before a restore" lists
a `before-restore-...zip`: that is what was here just before, in case you restored by mistake.

6. Click **Settings**, **Clients & environments**. Your clients and pods are there, and the test
   users still say the password is saved (it is kept on this computer).

To try a restore on a second computer: copy the zip there, restore it the same way. The clients and
users appear, and each user says the password is not saved yet: type it again.

In a terminal: `qm backup my-backup.zip`, and, with Quartermaster closed, `qm restore my-backup.zip`.

### 6.15b Automatic backups

1. Click **Settings**, then the **General** tab. Find **Automatic backups**.

You should see: "On: once a day after 02:00", the time, "Keep the newest 7", and "No automatic backup yet".
(Quartermaster checks a minute after it starts, so a backup may already be listed.)

2. Click **Back up now**.

You should see: "Backup made." and one row under **Saved copies** with today's time, a size and **Download**, **Restore**.

3. Type 99 in **Keep the newest** and click **Save**.

You should see: a red message "keep between 1 and 30 backups". Type 3, **Save**: "Saved."

4. Click **Back up now** four more times (wait a second between clicks, the file name has the time to the second).

You should see: only the newest 3 copies are listed.

5. Click **Download** on one and open the zip: it has `tests`, `data` and `backup.json`, like a normal backup.
6. Set **After** to a time a few minutes from now, untick **Make a backup every day**, **Save**, then wait past that time.

You should see: nothing new is made. Tick it again and **Save**: a new copy appears within a minute (the time has passed
and none was made since).

7. Open **Audit log**.

You should see: "Made an automatic backup", "Changed the automatic backup settings", each with the file or what changed. No secrets.

### 6.16 Retries, flaky tests and suggested fixes

**A. A step that fails is tried again**

1. Click **Settings**, then **Evidence**. Under **If a step fails**, choose **Try once more**.
2. Make sure the demo files are in `my_tests` (see 6.14, step 1).
3. Run **Retry demo (always fails, reads only)** from **Tests**.

You should see: the test fails, and its step says **Tried 2 times**. In the Word document the step
has an **Attempts** line: "2 (every attempt failed)". Now choose **Stop at once** in Settings and run
it again: the step says nothing about attempts (it was tried once).

In **Needs attention** this failure is listed as **Service call failed** (a service address that does not
exist, so the advice says to check the address), not as a check that did not match.

A test that passes only on the retry cannot be forced on purpose. When it happens for real, the
step says "Passed on attempt 2: the first try did not work (...)", the test shows **Flaky** after it
happens twice in 10 runs, and the Overview has a **Stability** card with the share of runs that needed
a retry.

**B. A suggested fix for a button that was renamed**

4. The test **Suggestion demo (renamed link, reads only)** looks for a link called `Location`. The link on the
   page is called "Locations", so it stands in for a name Oracle changed. (The suggestion may show the
   link's longer full name, for example "Locations Define locations...": that is how the page names it.)

5. Run the Suggestion demo. It fails at step 2 (about a minute, because the step is tried again first).
6. Click **Needs attention**. (If a failed run shows no suggestion, open the run, scroll to the bottom and open
   **Messages from the run**: a line "no suggested fix (...)" says why. Send me that line.)

You should see: under the failure, a blue box **Suggested fix**: "A similar name on the screen suggests
the step should find the link named "Locations" instead of the link named "Location"." The test file
is not changed yet.

7. Click **Use the suggestion**, then run the test again.

You should see: the run passes. Open the file: `- role: "link:Locations"` is the first way, and the old
`link:Location` is still there below it. A copy of the old file is in `.qm\backups`.

8. Only if an AI is set up (Settings, AI assistant): change the file to look for
   `link:Document Stuff` (a name nothing on the page looks like). Run it. If the AI recognises the
   screen it may suggest a link; if it is not sure it says nothing, and the failure has no suggestion.
   That is correct: a wrong suggestion is worse than none. With **Suggest a fix when a step cannot find its
   item** off, the AI is never asked.

Delete the demo files from `my_tests` when you are done.

### 6.17 Notifications when a run fails

You need one place to receive a message. Use whichever you have:

- a **Slack** or **Microsoft Teams** channel where you may add a webhook (Slack: Apps, Incoming Webhooks;
  Teams: Workflows, "When a Teams webhook request is received" and post to a channel), or
- a **mail server** you may send through (host, port, user and password), or
- for a harmless first try: a free test address from a web page such as webhook.site (it shows what was
  posted; the test message holds no secrets). Choose **Other (sends JSON)** and paste the address it gives you.

1. Click **Settings**, then the **Notifications** tab. A blue box says nothing is switched on.
2. In the Slack, Teams or other service box, choose the service, paste the address, tick
   **Send to this webhook** and click **Save**. (For e-mail, fill in the box below it instead.)
3. Click **Send a test message**.

You should see: "Sent to the webhook." (or "Sent to 1 recipient(s)." for e-mail) in green, and the message
"Test message from Quartermaster" in your channel or inbox. Under **Recent messages** the attempt is
listed. If it did not work, the text says why, for example "the webhook answered HTTP 404" or "the mail
server refused the user name or password". The address and password are not shown again; the box says
"Saved (hidden)".

4. Make a run fail on a schedule, which is what notifications are for. Copy the demo files if you have not
   (see 6.14), then open **Schedules**, **New schedule**: Name `Notify check`, what to test: **Retry demo
   (always fails, reads only)**, today only, a time two minutes ahead, **On** ticked. Save it, then click
   **Run now** on it so you need not wait.

You should see: when the run ends (about a minute), a message like "Acme: 1 of 1 test failed" in your
channel or inbox, naming **Retry demo**, the failed step and "service calls that failed". It does not
contain the pod's own text. **Recent messages** lists it, and the **Audit log** has "Sent a notification".

5. Start the same test yourself from **Tests**. You should see no message, because the default is
   scheduled runs only. In **When to send**, choose **Every run**, **Save**, and run it again: now a message comes.
6. Delete the schedule when you are done (open it, **Delete**), and switch notifications off if you only
   wanted to try them.

### 6.18 Approving a release

Do this after some tests have run with the Oracle release set in Settings (6.1).

1. Click **Overview**. In the release card (for example "26C release readiness") there is a line
   **APPROVAL** with **Not approved** and a button **Approve 26C…**.
2. Click **Approve 26C…**. A panel opens with the numbers (passed, failed, not run). Click **Approve 26C**
   without typing anything.

You should see: a red message "type your name". Nothing is recorded.

3. Type your name and your role (for example Test manager). If any test failed or has not run, the panel
   says so and shows a box. Click **Approve 26C** without ticking it.

You should see: a message that you must tick the box. Tick it and write a short comment (try 3 letters
first: it asks for at least 10), then click **Approve 26C**.

You should see: the panel closes and the card says **Approved**, with your name, the time, the numbers and
your comment. Click **History**: the record is there, marked "Approved knowing tests had failed or not run".

4. Click **Certification pack** and open the Word document in the zip. After the Summary there is an
   **Approval** section: your name, role, time, comment, the numbers when you approved, and "Approved with
   open items". The zip also holds `approvals.json`.
5. Run any test again (from **Tests**), then look at the card.

You should see: **Approved, results changed**, with how many tests changed. There is an **Approve again**
button. (If the test was run on the same release.)

6. Click **Withdraw**, type your name and a reason, and click **Withdraw the approval**.

You should see: the card says **Approval withdrawn** with your reason, and **Approve again**. **History**
now lists the approval and the withdrawal. The **Audit log** page has both too. Download the pack again: its
Approval section says "Approval withdrawn".

### 6.19 Sign-in and roles

Do this on a test copy or be ready to turn sign-in off again (step 11). Sign-in is off until you turn it on.

1. Click **Settings**, then **Users & sign-in**. A blue box says sign-in is off.
2. Type your full name, a user name (for example `sai`) and a password of at least 10 characters twice.
   Click **Turn on sign-in** and confirm.

You should see: the page now lists you as an Administrator ("you"), and the menu has an **Account** section
with your name and **Sign out**.

3. Click **Add a user**. Name `Jo Tester`, user name `jo`, leave **Tester** ticked, click **Add the user**.

You should see: a panel with a 12-character temporary password and the words "This is the only time it is
shown". Copy it. Click **Done**.

4. Open a second browser (or a private window) and go to http://127.0.0.1:8765

You should see: only a sign-in card, no menu. Try a wrong password: "wrong user name or password".

5. Sign in as `jo` with the temporary password.

You should see: "Choose your own password". Type the temporary one, a new one twice (the two must match) and save.

6. Look at Jo's menu and the Overview.

You should see: Jo can run and record, but there is **no Settings** in the menu, and no **Approve** button on the
release card. In the address bar type `#/settings?tab=users`: "this needs an administrator".

7. Back as the administrator: **Settings, Users & sign-in**, click **Change** next to Jo, tick **Approver** too, **Save**.
   In Jo's browser, sign out and in again (or press F5): the **Approve** button is there.
8. Approve the release as Jo (see 6.18).

You should see: the approval says "Jo Tester", whatever else is typed, and the certification pack says "Signed in as jo".

9. As the administrator, open **Audit log**.

You should see: signing in, adding the user, changing the roles, the approval, each with a name. No passwords.

10. Click **Change** next to Jo, **Reset password**: a new temporary password is shown once, and Jo is signed out.
    Try signing in as `sai` with a wrong password 5 times: the 6th says to try again in 15 minutes (even with the
    right password).
11. To turn it off: **Settings, Users & sign-in**, type your password, **Turn off sign-in**. Quartermaster is
    open again, as before. If you ever cannot sign in: in a terminal on this computer run `qm users disable-signin`.

### 6.20 Sign in with Google

Needs sign-in on (6.19) and a Gmail address. Follow the five Google steps in the README, section "Sign in with
Google". Open Quartermaster at **http://localhost:8765** (not 127.0.0.1).

1. **Settings, Users & sign-in**: under **Sign in with Google** the exact redirect address is shown. Paste the Client ID
   and the Client secret, tick **Turn on Continue with Google**, click **Save**.

You should see: "Saved." and the card says "On". The secret box now says "Saved".

2. **Add a user**: name `Me on Gmail`, your own Gmail address, tick **Google only**, keep Tester. Click **Add the user**.

You should see: "can now sign in with Google" and no temporary password. The row has a **Google only** badge.

3. In a private window open http://localhost:8765.

You should see: a **Continue with Google** button above the user name and password.

4. Click it, choose your Gmail (Google may say "unverified app": Advanced, continue, since it is your own app).

You should see: you land in Quartermaster signed in as that user.

5. Sign out, click **Continue with Google** with a different Gmail that is not on the list.

You should see: the sign-in page with "... has not been given access to Quartermaster. Ask an administrator to add that address."

6. As the administrator, **Audit log**.

You should see: "Signed in with Google" and "Google sign-in refused", each with the address. No secrets.

7. To turn it off: untick **Turn on Continue with Google**, Save. The button disappears.

### 6.21 Shared steps

Read only, safe on your pod (same as the demos in 6.14).

1. Copy the demos again, this time with the shared folder:

   ```powershell
   Copy-Item examples\demos\* my_tests\ -Recurse
   ```

   Press F5 in Quartermaster. Click **Shared steps** in the menu.

You should see: one card, **Read some locations (reads only)**, "used by 2 tests", with its one step,
"A test can hand in how_many (if not given: 1)", and the two demo tests listed.

2. Click **Tests**, open **Shared steps demo two**, then the **Steps** tab.

You should see: one step "Find 2 location(s)" with a small tag **shared: read-locations**.

3. Run **Shared steps demo one** and **demo two**.

You should see: both pass. Each shows a blue box **Test data cleaned up** (the group's cleanup was added to each test).

4. Open `my_tests\_library\read-locations.yaml` in Notepad. Change `locationsV2?limit=` to `locationsV9?limit=` and save. Run both demos.

You should see: **both** fail at step 1, from one change in one file. Put it back to `locationsV2` and both pass again.

5. In Notepad, in `my_tests\library_demo_one.yaml`, change `use: read-locations` to `use: read-locationz`. Open **Shared steps**.

You should see: a red box "A test uses shared steps that do not exist. 'read-locationz'". The test shows as unreadable in
**Needs attention** with a message naming the groups that do exist. Change it back.

6. Delete the demo files from `my_tests` when you are done (including `_library\read-locations.yaml`).

### 6.22 Reading Oracle's What's New

Uses a small sample page that comes with Quartermaster, so it needs no Oracle sign-in. Nothing is saved until you choose Save.

1. Click **Release impact**, then **Import feature list**. Choose the file `examples\releases\26D_whats_new_sample.html`.

You should see: the release box fills in with **26D**, and "4 features found for release 26D". **Columns used** says
"Feature (table)" and "the text under each feature's heading". The first features are listed with their product,
module, and "opt-in" on **New Personal Details Page** only. **Invoice Approval by Line** says Financials and BOTH.

2. Click **What the page says** under a feature.

You should see: the page's own words for it, for example for Redwood Worker Search: "Search for workers faster..." and the
tip about the older page, nothing rewritten.

3. Click **Save feature list**. Choose **26D.json** at the top if it is not already shown.

You should see: the plan for 26D with those four features. Tests that mention search, personal details, locations or
invoices are matched to them.

4. Open the import again. Instead of a file, paste the contents of `examples\releases\26D_whats_new_sample.txt` into the
   box **Or paste text** and click **Check file**.

You should see: "2 features found for release 26D" (the text has two features).

5. Now try your own: open a real What's New page of your update in your browser, save it as HTML only, and import it.
   Look at the preview. If products or opt-in marks look wrong, tell me what the page looks like (a screenshot of the
   page and of the preview) and I will adjust the reading.

### 6.23 Running tests at the same time

Safe on your pod: it uses the read-only demo tests (copy them as in 6.21 if they are not in `my_tests`).

1. Click **Settings**, then the **Evidence** tab. Find **Tests at the same time**. It says **One at a time**.
2. Run all the demo tests once as they are (**Run all tests**, or **New run** with the folder `my_tests`). Note the **Duration**
   on the run page.
3. Click **2** under **Tests at the same time**.

You should see: "Saved. Runs started from now on use it."

4. Run the same tests again and open the run page while it runs.

You should see: while it runs, "2 tests running at the same time (0 of 5 finished)", counting up. When it ends: the same
results as before, in the same order, and a fact **Tests at once: 2 at the same time**. The **Duration** is shorter (with
read-only demos the gain is small; with 20 or more tests it is large).

5. Open the evidence of two of the tests: each has its own folder, screenshots and Word document.
6. In one demo file add the line `tags: [serial]` (under `priority:`) and run again with 2.

You should see: that test runs by itself after the other tests have finished.

7. Set it back to **One at a time** when you are done if you prefer. If two tests ever disturb each other, tell me which
   two and what they change.

## Part 7. Stop

Press Ctrl+C in the terminal running `qm serve`.

Where things are kept:

- `evidence\` holds screenshots, videos and Word documents of every run.
- `.qm\` holds the run history, settings, imported feature lists and imported manual scripts.

Keep `.qm\`: deleting it also deletes your imported manual scripts and run history. The scenarios
you did by hand or prepared are saved as tests in `my_tests\manual\`. `my_tests` is yours: back it
up. It is not part of the Quartermaster repository, so it is never committed or overwritten by a pull.

## Reporting a problem

Send these four things:

1. Which part and step (for example "6.6 step 7").
2. What you expected and what you saw.
3. A screenshot of the page.
4. The last 30 lines of the terminal. Remove the password if it appears anywhere.
