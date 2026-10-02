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
