"""Batch scheduling engine for group sessions."""
from datetime import datetime, timedelta
from collections import defaultdict
import math


def parse_time(t_str):
    """Parse HH:MM to (hour, minute)."""
    parts = t_str.strip().split(':')
    return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def is_graveyard_shift(shift_str):
    """Determine if a shift is graveyard (18:00-03:00 range)."""
    h, m = parse_time(shift_str)
    # Graveyard: 18:00 (6pm) to 03:00 (3am) — wraps midnight
    return h >= 18 or h <= 3


def schedule_batches(roster, leaves, week_start, num_weekdays, batch_configs,
                     sessions_per_rep, respect_off_day, respect_leaves,
                     balance_by_role, num_weeks, separate_graveyard):
    """
    Batch scheduling engine.

    Args:
        roster: list of rep dicts
        leaves: dict of workday_id -> list of leave dates
        week_start: datetime.date
        num_weekdays: int (typically 5)
        batch_configs: list of (batch_time_str, preferred_size_or_None) tuples
                       e.g., [('10:00', 15), ('14:00', None)]
        sessions_per_rep: int (how many batch sessions each rep attends)
        respect_off_day: bool
        respect_leaves: bool
        balance_by_role: bool (proportionally distribute roles across batches)
        num_weeks: int
        separate_graveyard: bool (keep graveyard batches on different days)

    Returns:
        dict with:
            scheduled: list of session dicts (one row per rep per session)
            unscheduled: list of (rep, sessions_placed, reason, week) tuples
            batch_summary: list of batch dicts for reporting
    """

    # Separate reps by shift category
    graveyard_reps = []
    dayshift_reps = []

    for rep in roster:
        if separate_graveyard and is_graveyard_shift(rep['shift_time']):
            graveyard_reps.append(rep)
        else:
            dayshift_reps.append(rep)

    # Build week date ranges
    all_weeks = []
    for w in range(num_weeks):
        base = week_start + timedelta(days=w * 7)
        week_dates = [base + timedelta(days=d) for d in range(num_weekdays)]
        all_weeks.append(week_dates)

    # Determine day allocation if separating graveyard
    dayshift_days = []
    graveyard_days = []

    if separate_graveyard and graveyard_reps:
        # Allocate days: graveyard gets ~40%, dayshift gets ~60%
        graveyard_count = max(1, int(num_weekdays * 0.4))
        # Graveyard: Mon, Wed (indices 0, 2)
        # Dayshift: Tue, Thu, Fri (indices 1, 3, 4)
        for week_dates in all_weeks:
            graveyard_days.extend([week_dates[i] for i in range(0, min(graveyard_count, len(week_dates)), 2)])
            dayshift_days.extend([week_dates[i] for i in range(len(week_dates)) if i not in range(0, min(graveyard_count, len(week_dates)), 2)])
    else:
        # All reps share all days
        dayshift_days = [d for week in all_weeks for d in week]
        graveyard_days = []

    scheduled = []
    unscheduled = []
    batch_summary = []

    # Process dayshift batches
    if dayshift_reps:
        day_result = _schedule_rep_group(
            dayshift_reps, leaves, dayshift_days if dayshift_days else [d for week in all_weeks for d in week],
            batch_configs, sessions_per_rep, respect_off_day, respect_leaves,
            balance_by_role, 'Day Shift', all_weeks
        )
        scheduled.extend(day_result['scheduled'])
        unscheduled.extend(day_result['unscheduled'])
        batch_summary.extend(day_result['batch_summary'])

    # Process graveyard batches (if separate)
    if separate_graveyard and graveyard_reps:
        grave_result = _schedule_rep_group(
            graveyard_reps, leaves, graveyard_days,
            batch_configs, sessions_per_rep, respect_off_day, respect_leaves,
            balance_by_role, 'Graveyard Shift', all_weeks
        )
        scheduled.extend(grave_result['scheduled'])
        unscheduled.extend(grave_result['unscheduled'])
        batch_summary.extend(grave_result['batch_summary'])

    return {
        'scheduled': scheduled,
        'unscheduled': unscheduled,
        'batch_summary': batch_summary
    }


def _schedule_rep_group(reps, leaves, available_days, batch_configs, sessions_per_rep,
                        respect_off_day, respect_leaves, balance_by_role, group_name, all_weeks):
    """Schedule a group of reps (dayshift or graveyard) into batches."""

    scheduled = []
    unscheduled = []
    batch_summary = []

    if not available_days or not reps:
        return {'scheduled': [], 'unscheduled': [], 'batch_summary': []}

    # Filter reps by availability
    eligible_reps = []
    for rep in reps:
        wd_id = rep['workday_id']
        off_day = rep['off_day'].lower() if respect_off_day else ''

        # Find available days for this rep
        rep_available_days = []
        for day_date in available_days:
            day_name = day_date.strftime('%A').lower()

            # Check off-day
            if off_day and day_name.startswith(off_day[:3]):
                continue

            # Check leaves
            if respect_leaves and wd_id in leaves and day_date in leaves[wd_id]:
                continue

            rep_available_days.append(day_date)

        if len(rep_available_days) >= sessions_per_rep:
            eligible_reps.append((rep, rep_available_days))
        else:
            # Find which week this was
            week_num = 1
            unscheduled.append((rep, 0, f"Not enough working days ({len(rep_available_days)} available, {sessions_per_rep} needed)", week_num))

    if not eligible_reps:
        return {'scheduled': scheduled, 'unscheduled': unscheduled, 'batch_summary': batch_summary}

    # Group reps by role for balanced distribution
    if balance_by_role:
        roles = defaultdict(list)
        for rep, days in eligible_reps:
            roles[rep['role']].append((rep, days))
    else:
        roles = {'All': eligible_reps}

    # Calculate total batches needed
    total_reps = len(eligible_reps)

    # Auto-calculate batch size if not specified
    auto_batch_sizes = []
    for batch_time, pref_size in batch_configs:
        if pref_size and pref_size > 0:
            auto_batch_sizes.append(pref_size)
        else:
            # Auto: divide reps evenly across all batches
            num_batches_per_week = len(batch_configs) * sessions_per_rep
            auto_size = math.ceil(total_reps / num_batches_per_week)
            auto_batch_sizes.append(auto_size)

    # Build batch slots: each batch config × sessions_per_rep × available_days
    batch_slots = []
    batch_id = 1

    for week_dates in all_weeks:
        week_num = all_weeks.index(week_dates) + 1
        # Filter to days in this week
        week_day_dates = [d for d in available_days if d in week_dates]

        for day_date in week_day_dates:
            for idx, (batch_time_str, pref_size) in enumerate(batch_configs):
                batch_size = auto_batch_sizes[idx]
                h, m = parse_time(batch_time_str)

                batch_slots.append({
                    'id': batch_id,
                    'date': day_date,
                    'time': batch_time_str,
                    'hour': h,
                    'minute': m,
                    'group': group_name,
                    'week': week_num,
                    'capacity': batch_size,
                    'reps': [],  # Will hold assigned reps
                    'role_counts': defaultdict(int)
                })
                batch_id += 1

    # Assign reps to batches with role balance
    rep_assignments = defaultdict(list)  # rep_id -> list of batch_ids

    # For each rep, assign to sessions_per_rep batches
    for rep, rep_days in eligible_reps:
        wd_id = rep['workday_id']
        role = rep['role']

        # Find eligible batch slots for this rep (on their available days)
        eligible_batches = [b for b in batch_slots if b['date'] in rep_days]

        if len(eligible_batches) < sessions_per_rep:
            unscheduled.append((rep, 0, f"Not enough batch slots on available days", 1))
            continue

        # Greedy assignment: pick sessions_per_rep slots with lowest current occupancy
        # (and maintain role balance if enabled)
        assigned_count = 0
        assigned_batches = []

        for _ in range(sessions_per_rep):
            best_batch = None
            best_score = float('inf')

            for batch in eligible_batches:
                if batch in assigned_batches:
                    continue  # Already assigned to this batch

                # Check capacity
                if len(batch['reps']) >= batch['capacity']:
                    continue

                # Score: prefer less-filled batches, and if balance_by_role,
                # prefer batches where this role is underrepresented
                occupancy = len(batch['reps'])
                role_imbalance = 0

                if balance_by_role and batch['reps']:
                    # Calculate how far this role is from its target proportion
                    total_in_batch = len(batch['reps'])
                    role_in_batch = batch['role_counts'][role]
                    # Target: role should be proportional to its roster share
                    total_role_reps = len([r for r, _ in eligible_reps if r['role'] == role])
                    target_ratio = total_role_reps / total_reps if total_reps > 0 else 0
                    current_ratio = role_in_batch / total_in_batch if total_in_batch > 0 else 0
                    role_imbalance = abs(current_ratio - target_ratio)

                score = occupancy * 10 + role_imbalance * 100

                if score < best_score:
                    best_score = score
                    best_batch = batch

            if best_batch:
                best_batch['reps'].append(rep)
                best_batch['role_counts'][role] += 1
                assigned_batches.append(best_batch)
                assigned_count += 1

        if assigned_count < sessions_per_rep:
            unscheduled.append((rep, assigned_count, "No free batch slot (capacity)", 1))
        else:
            # Create session records for each assigned batch
            for batch in assigned_batches:
                session = {
                    'workday_id': wd_id,
                    'pseudo_name': rep['pseudo_name'],
                    'email': rep['email'],
                    'manager': rep['manager'],
                    'role': rep['role'],
                    'shift_time': rep['shift_time'],
                    'off_day': rep['off_day'],
                    'schedule_day': batch['date'].strftime('%A'),
                    'schedule_date': batch['date'],
                    'session_start_time': batch['time'],
                    'session_end_time': batch['time'],  # Batch doesn't have end time (group session)
                    'week': batch['week'],
                    'batch_id': batch['id'],
                    'batch_group': group_name
                }
                scheduled.append(session)

    # Build batch summary for reporting
    for batch in batch_slots:
        if batch['reps']:
            role_breakdown = dict(batch['role_counts'])
            batch_summary.append({
                'batch_id': batch['id'],
                'date': batch['date'],
                'time': batch['time'],
                'group': batch['group'],
                'week': batch['week'],
                'capacity': batch['capacity'],
                'actual_count': len(batch['reps']),
                'role_breakdown': role_breakdown,
                'reps': [r['pseudo_name'] for r in batch['reps']]
            })

    return {
        'scheduled': scheduled,
        'unscheduled': unscheduled,
        'batch_summary': batch_summary
    }
