# 📅 Session Planner

A Flask web application for scheduling coaching sessions with advanced constraint handling, multi-window support, and interactive visualizations.

This app is intended to help plan sessions requested by stakeholders, such as enablement sessions, internal team meetings, and similar events, based on a few constraints provided by the user.

## Features

### Core Scheduling
- **Multiple scheduling windows** — Add any number of time windows, optionally bound to specific roles
- **Multi-week scheduling** — Repeat the full session set across multiple weeks
- **Configurable constraints**:
  - Sessions per rep, session length, max reps per slot
  - Minimum gap between sessions (e.g., ≥1 day)
  - One manager per slot (prevents manager conflicts)
  - Respect off-days and approved leaves
  - Shift-aware placement (reps scheduled within their 9-hour shift window)
  - Daily load balancing

### Reports & Visualization
- **Interactive charts** (Chart.js):
  - Sessions per day (stacked by manager or role)
  - Total sessions by manager/role
  - Day-by-day totals
  - Manager/role share (doughnut charts)
  - Filter by manager or role
- **Unscheduled reps report** — Web view + Excel sheet with reasons
- **Excel workbook export** with 6 sheets:
  - Final Schedule (long format with Session Start/End Time)
  - Unscheduled Reps
  - Calendar Grid
  - Daily Balance
  - Windows & Rules
  - Leave Adjustments

### Google Sheets Integration
- One-click export to Google Sheets
- OAuth 2.0 authentication
- All sheets written as tabs in a new spreadsheet

## Installation

### Requirements
- Python 3.9+
- pip

### Setup

1. **Clone or unzip** the project:
   ```bash
   cd Session_Planner
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Mac/Linux
   # or
   venv\Scripts\Activate.ps1  # Windows PowerShell
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **(Optional) Google Sheets setup**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the **Google Sheets API** and **Google Drive API**
   - Create **OAuth 2.0 credentials** (Desktop app)
   - Download the JSON and save as `client_secret.json` in the project root
   - First export will prompt for OAuth consent; token is cached in `token.json`

5. **Run the app**:
   ```bash
   python app.py
   ```

6. **Open in browser**:
   ```
   http://localhost:5000
   ```

## Usage

### 1. Upload Files
- **Agents Data (required)**: Excel file with columns:
  - `Workday ID`, `Pseudo Name`, `Email`, `Manager`, `Role/JD`, `Shift Time`, `Off Day`
- **Leave Tracker (optional)**: Excel file with a `Workday Data` sheet containing:
  - `Employee ID`, `Time Off Date`, `Status` (only "Approved" leaves are used)

### 2. Configure Scheduling Windows
- Add one or more time windows (e.g., 09:00 – 14:00)
- Optionally bind roles to windows:
  - Leave blank → applies to all reps
  - Enter roles (comma-separated) → only those roles schedule in that window

### 3. Set Week & Days
- Choose the starting Monday
- Select number of weekdays (typically 5 for Mon–Fri)
- **Multi-week option**: Check "Repeat this schedule" and set an end date to schedule across multiple weeks

### 4. Session Settings
- Sessions per rep (default 2)
- Session length in minutes (default 30)
- Minimum gap between sessions (default 1 day)
- Max reps per slot (default 5)

### 5. Apply Constraints
- **One manager per slot**: Prevents two reps under the same manager in one slot
- **Respect Off Days**: Excludes reps' designated off-days
- **Respect Leaves**: Excludes dates from the leave tracker
- **Shift-aware placement**: Places reps only in slots overlapping their shift
- **Balance daily load**: Distributes sessions evenly across days

### 6. Generate & Download
- Click **Generate Schedule**
- View summary stats, charts, and unscheduled details
- Download the Excel workbook or export to Google Sheets

## Output Format

### Final Schedule Columns
- `Workday_ID`, `Pseudo_Name`, `Email`, `Manager`, `Role/JD`
- `Shift_Time`, `Off_Day`
- `Week` (if multi-week)
- `Schedule_Day`, `Schedule_Date`
- **`Session Start Time`**, **`Session End Time`**

### Unscheduled Reps Sheet
For any rep who didn't receive the full number of sessions, includes:
- ID, Name, Manager, Role, Week (if multi-week)
- Sessions Needed, Placed, Missing
- **Reason** (e.g., "Not enough working days", "No free slot", "Role not mapped to window")
- **Detail** (full explanation)

## Troubleshooting

### Port 5000 Already in Use
Common on macOS (AirPlay uses 5000). Edit the last line of `app.py`:
```python
app.run(debug=True, port=5001)
```
Then open `http://localhost:5001`.

### Google Sheets Export Fails
- Ensure `client_secret.json` exists (see step 4 in Setup)
- Check that Google Sheets API and Drive API are enabled in your Cloud project
- Delete `token.json` and retry if credentials are stale

### "python" Not Found
Use `python3` instead of `python` on Mac/Linux.

### Workbook Has Missing Data
- Check that your roster file has the expected columns (flexible matching, but at least ID, Name, Manager, Shift Time, Off Day)
- Verify the leave file has a `Workday Data` sheet with Employee ID, Time Off Date, Status

## Architecture

```
Session_Planner/
├── app.py                  # Flask routes: upload, schedule, download, export
├── scheduler/
│   ├── loader.py           # Reads roster + Leave Tracker
│   ├── engine.py           # Core scheduling algorithm
│   ├── workbook.py         # Builds Excel workbook
│   └── gsheets.py          # Google Sheets OAuth + export
├── templates/
│   ├── index.html          # Upload form + constraint inputs
│   ├── result.html         # Summary, charts, download
│   └── gsheets_success.html
├── static/
│   └── style.css           # Responsive, dark-friendly styling
├── requirements.txt
├── .gitignore
└── README.md
```

## License

MIT

## Contributing

Pull requests welcome. For major changes, please open an issue first to discuss what you'd like to change.

## Support

For questions or issues, please open a GitHub issue at: https://github.com/ramish4890/Session_Planner/issues
