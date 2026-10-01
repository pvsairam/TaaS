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

3. Tell Quartermaster where the pod is and how to sign in. These last only for this terminal
   window. Do not put them in any file.

   ```powershell
   $env:QM_FUSION_URL="https://<your pod>.fa.us6.oraclecloud.com"
   $env:QM_FUSION_USER="<user name>"
   $env:QM_FUSION_PASSWORD="<password>"
   ```

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
qm serve --tests examples/tests
```

You should see: the terminal says `Quartermaster is running at http://127.0.0.1:8765` and your
browser opens that page. Keep this terminal open while you test. Press Ctrl+C in it to stop.

The left side has the menu: Overview, Runs, Tests, Release impact, Needs attention,
Record a test, Settings.

### 6.1 Settings

1. Click **Settings**.
2. Type a name for the environment (for example `DEV2`) and the Oracle release (for example `26C`). Click **Save**.
3. Click **Check now**.

You should see: the pod address, your user name, the password shown as set (never the password
itself), and a message that the pod answered.

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

To do a scenario by hand again (for example after Oracle changed the screen), open it and click
**Do it by hand**. Only run scenarios by hand that are safe to repeat on the test pod: whatever
you click, including Save or Submit, is played again every time.

**Other things to check**

- The **Result** column shows Quartermaster's own last result. "Workbook: Pass" in Notes only
  repeats what someone typed in the workbook's Pass / Fail column.
- Scenarios with `<>` in their steps are marked "Test data missing".
- In **Release impact**, the **Manual scenarios** tab lists the scenarios that cover a feature
  of the release. In the **Features** tab, a feature only a manual script covers is "Manual only".
- To remove a workbook: **Imported files**, then **Remove**. To update one, import it again.

### 6.8 Needs attention

1. Click **Needs attention**.

You should see: failed runs grouped by kind (for example "Item not found"), with the failed step,
what was expected, what was found and a screenshot. If nothing failed it says all clear.

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

### 6.10 Search and shortcuts

- Press **Ctrl+K**. Type `release impact`. Press Enter. It opens Release impact.
- Press **N**. The New run panel opens. Press Esc to close it.
- Click the moon or sun icon at the top. The page switches between dark and light.

## Part 7. Stop

Press Ctrl+C in the terminal running `qm serve`.

Where things are kept:

- `evidence\` holds screenshots, videos and Word documents of every run.
- `.qm\` holds the run history, settings, imported feature lists and imported manual scripts.

Keep `.qm\`: deleting it also deletes your imported manual scripts and run history. The scenarios
you did by hand are saved as tests in `examples\tests\manual\` (or in your own tests folder).

## Reporting a problem

Send these four things:

1. Which part and step (for example "6.6 step 7").
2. What you expected and what you saw.
3. A screenshot of the page.
4. The last 30 lines of the terminal. Remove the password if it appears anywhere.
