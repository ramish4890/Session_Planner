"""Flask app for Session Planner."""
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session as flask_session
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
from collections import Counter

from scheduler.loader import load_roster, load_leaves
from scheduler.engine import schedule_sessions, parse_time
from scheduler.workbook import build_workbook

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global to hold the last generated workbook
last_workbook = None
last_result = None


@app.route('/')
def index():
    """Main upload and configuration page."""
    return render_template('index.html')


@app.route('/schedule', methods=['POST'])
def schedule():
    """Process upload and generate schedule."""
    global last_workbook, last_result

    # Get uploaded files
    agents_file = request.files.get('agents_file')
    leaves_file = request.files.get('leaves_file')

    if not agents_file:
        flash('Please upload agents data file', 'error')
        return redirect(url_for('index'))

    # Save uploads
    agents_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(agents_file.filename))
    agents_file.save(agents_path)

    leaves_path = None
    if leaves_file:
        leaves_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(leaves_file.filename))
        leaves_file.save(leaves_path)

    # Parse form parameters
    try:
        week_start_str = request.form.get('week_start', '')
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()

        num_weekdays = int(request.form.get('num_weekdays', 5))
        sessions_per_rep = int(request.form.get('sessions_per_rep', 2))
        session_minutes = int(request.form.get('session_minutes', 30))
        max_per_slot = int(request.form.get('max_per_slot', 5))
        gap_days = int(request.form.get('gap_days', 1))

        one_manager_per_slot = request.form.get('one_manager_per_slot') == 'on'
        respect_off_day = request.form.get('respect_off_day') == 'on'
        respect_leaves = request.form.get('respect_leaves') == 'on'
        shift_aware = request.form.get('shift_aware') == 'on'
        balance_days = request.form.get('balance_days') == 'on'

        # Parse windows
        windows = []
        window_count = int(request.form.get('window_count', 1))

        for i in range(1, window_count + 1):
            start_time = request.form.get(f'window_{i}_start', '09:00')
            end_time = request.form.get(f'window_{i}_end', '14:00')
            roles_str = request.form.get(f'window_{i}_roles', '').strip()

            start_h, start_m = parse_time(start_time)
            end_h, end_m = parse_time(end_time)

            roles_list = None
            if roles_str:
                roles_list = [r.strip() for r in roles_str.split(',') if r.strip()]

            windows.append((start_h, start_m, end_h, end_m, roles_list))

        # Multi-week support
        num_weeks = 1
        repeat_weeks = request.form.get('repeat_weeks') == 'on'
        if repeat_weeks:
            week_end_str = request.form.get('week_end', '')
            if week_end_str:
                week_end = datetime.strptime(week_end_str, '%Y-%m-%d').date()
                num_weeks = ((week_end - week_start).days // 7) + 1

    except Exception as e:
        flash(f'Invalid form parameters: {e}', 'error')
        return redirect(url_for('index'))

    # Load data
    try:
        roster = load_roster(agents_path)
        leaves = load_leaves(leaves_path) if leaves_path else {}
    except Exception as e:
        flash(f'Error loading files: {e}', 'error')
        return redirect(url_for('index'))

    # Run scheduler
    try:
        result = schedule_sessions(
            roster, leaves, week_start, num_weekdays, windows, sessions_per_rep,
            session_minutes, max_per_slot, gap_days, one_manager_per_slot,
            respect_off_day, respect_leaves, shift_aware, balance_days, num_weeks
        )

        scheduled = result['scheduled']
        unscheduled = result['unscheduled']

        # Build workbook
        wb = build_workbook(scheduled, unscheduled, roster, num_weeks)

        # Save for download
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'schedule_output.xlsx')
        wb.save(output_path)

        last_workbook = output_path
        last_result = result

        # Prepare chart data
        chart_rows = []
        for session in scheduled:
            chart_rows.append({
                'manager': session['manager'],
                'role': session['role'],
                'date': session['schedule_date'].strftime('%Y-%m-%d'),
                'day': session['schedule_day']
            })

        # Get unique managers and roles for filters
        managers = sorted(set(r['manager'] for r in chart_rows))
        roles = sorted(set(r['role'] for r in chart_rows))

        # Summary stats
        total_sessions = len(scheduled)
        total_reps = len(set(s['workday_id'] for s in scheduled))
        unscheduled_count = len(unscheduled)
        missing_sessions = sum(sessions_per_rep - placed for _, placed, _, _ in unscheduled)

        # Prepare unscheduled details for web view
        unscheduled_details = []
        for rep, placed, reason, week in unscheduled:
            unscheduled_details.append({
                'workday_id': rep['workday_id'],
                'name': rep['pseudo_name'],
                'manager': rep['manager'],
                'role': rep['role'],
                'week': week if num_weeks > 1 else None,
                'needed': sessions_per_rep,
                'placed': placed,
                'missing': sessions_per_rep - placed,
                'reason': reason,
                'detail': f"{rep['pseudo_name']} needed {sessions_per_rep} but got {placed}. {reason}."
            })

        return render_template('result.html',
                             total_sessions=total_sessions,
                             total_reps=total_reps,
                             unscheduled_count=unscheduled_count,
                             missing_sessions=missing_sessions,
                             unscheduled_details=unscheduled_details,
                             chart_rows=chart_rows,
                             managers=managers,
                             roles=roles,
                             num_weeks=num_weeks)

    except Exception as e:
        flash(f'Error during scheduling: {e}', 'error')
        return redirect(url_for('index'))


@app.route('/download')
def download():
    """Download the generated schedule."""
    global last_workbook

    if not last_workbook or not os.path.exists(last_workbook):
        flash('No schedule available to download', 'error')
        return redirect(url_for('index'))

    return send_file(last_workbook, as_attachment=True, download_name='Session_Schedule.xlsx')


@app.route('/export_gsheets')
def export_gsheets():
    """Export to Google Sheets."""
    global last_workbook

    if not last_workbook or not os.path.exists(last_workbook):
        flash('No schedule available to export', 'error')
        return redirect(url_for('index'))

    try:
        from openpyxl import load_workbook
        from scheduler.gsheets import export_to_gsheets

        wb = load_workbook(last_workbook)
        url = export_to_gsheets(wb, title=f"Session Schedule {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        return render_template('gsheets_success.html', url=url)

    except FileNotFoundError as e:
        flash(str(e), 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error exporting to Google Sheets: {e}', 'error')
        return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
