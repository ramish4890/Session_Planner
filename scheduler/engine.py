"""Core scheduling engine with all constraints."""
from datetime import datetime, timedelta
from collections import defaultdict


def parse_time(t_str):
    """Parse HH:MM or H:MM to (hour, minute) tuple."""
    parts = t_str.strip().split(':')
    return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def time_to_minutes(h, m):
    """Convert hour:minute to minutes since midnight."""
    return h * 60 + m


def overlaps_shift(slot_h, slot_m, shift_start_str, shift_hours=9):
    """Check if a slot time falls within a rep's shift window."""
    slot_min = time_to_minutes(slot_h, slot_m)
    shift_h, shift_m = parse_time(shift_start_str)
    shift_min = time_to_minutes(shift_h, shift_m)
    shift_end_min = shift_min + shift_hours * 60

    # Handle wrap-around (e.g., 21:00 + 9h = 06:00 next day)
    if shift_end_min >= 1440:  # crosses midnight
        return slot_min >= shift_min or slot_min < (shift_end_min % 1440)
    else:
        return shift_min <= slot_min < shift_end_min


def schedule_sessions(roster, leaves, week_start, num_weekdays, windows, sessions_per_rep,
                      session_minutes, max_per_slot, gap_days, one_manager_per_slot,
                      respect_off_day, respect_leaves, shift_aware, balance_days, num_weeks):
    """
    Main scheduling engine.

    Args:
        roster: list of rep dicts
        leaves: dict of workday_id -> list of leave dates
        week_start: datetime.date for first day
        num_weekdays: int (typically 5 for Mon-Fri)
        windows: list of (start_h, start_m, end_h, end_m, roles_list_or_None)
        sessions_per_rep: int
        session_minutes: int
        max_per_slot: int
        gap_days: int (minimum days between sessions)
        one_manager_per_slot: bool
        respect_off_day: bool
        respect_leaves: bool
        shift_aware: bool
        balance_days: bool
        num_weeks: int (1 for single week, >1 for multi-week)

    Returns:
        dict with:
            scheduled: list of session dicts
            unscheduled: list of (rep, sessions_placed, reason) tuples
            slots_grid: dict for calendar view
    """
    scheduled = []
    unscheduled = []

    # Build week date ranges
    all_weeks = []
    for w in range(num_weeks):
        base = week_start + timedelta(days=w * 7)
        week_dates = [base + timedelta(days=d) for d in range(num_weekdays)]
        all_weeks.append(week_dates)

    # Process each week independently
    for week_idx, week_dates in enumerate(all_weeks):
        week_num = week_idx + 1

        # Build slot grid for this week
        slots = defaultdict(lambda: {'reps': [], 'managers': set()})

        for rep in roster:
            wd_id = rep['workday_id']
            name = rep['pseudo_name']
            manager = rep['manager']
            role = rep['role']
            shift = rep['shift_time']
            off_day = rep['off_day'].lower() if respect_off_day else ''

            # Find eligible windows for this rep
            eligible_windows = []
            for win_start_h, win_start_m, win_end_h, win_end_m, win_roles in windows:
                if win_roles:  # Role-bound window
                    if role in win_roles:
                        eligible_windows.append((win_start_h, win_start_m, win_end_h, win_end_m))
                else:  # Open to all
                    eligible_windows.append((win_start_h, win_start_m, win_end_h, win_end_m))

            if not eligible_windows:
                unscheduled.append((rep, 0, f"Role '{role}' not mapped to any scheduling window", week_num))
                continue

            # Find available days (exclude off-days and leaves)
            available_days = []
            for day_date in week_dates:
                day_name = day_date.strftime('%A').lower()

                # Check off-day
                if off_day and day_name.startswith(off_day[:3]):
                    continue

                # Check leaves
                if respect_leaves and wd_id in leaves and day_date in leaves[wd_id]:
                    continue

                available_days.append(day_date)

            # Check if enough days for sessions with gap
            if len(available_days) < sessions_per_rep:
                unscheduled.append((rep, 0, f"Not enough working days ({len(available_days)} available, {sessions_per_rep} needed)", week_num))
                continue

            # Build slot candidates for this rep
            candidates = []
            for day_date in available_days:
                for win_start_h, win_start_m, win_end_h, win_end_m in eligible_windows:
                    # Generate slots within this window
                    slot_h, slot_m = win_start_h, win_start_m
                    while True:
                        slot_end_min = time_to_minutes(slot_h, slot_m) + session_minutes
                        slot_end_h = slot_end_min // 60
                        slot_end_m = slot_end_min % 60

                        if slot_end_h > win_end_h or (slot_end_h == win_end_h and slot_end_m > win_end_m):
                            break

                        # Check shift overlap if shift_aware
                        if shift_aware and not overlaps_shift(slot_h, slot_m, shift, 9):
                            # Move to next slot
                            slot_m += session_minutes
                            slot_h += slot_m // 60
                            slot_m = slot_m % 60
                            continue

                        candidates.append((day_date, slot_h, slot_m, slot_end_h, slot_end_m))

                        # Move to next slot
                        slot_m += session_minutes
                        slot_h += slot_m // 60
                        slot_m = slot_m % 60

            if not candidates:
                unscheduled.append((rep, 0, "No eligible time slots in shift window", week_num))
                continue

            # Try to place sessions_per_rep sessions with gap constraint
            placed = []
            for _ in range(sessions_per_rep):
                best_slot = None

                for day_date, slot_h, slot_m, slot_end_h, slot_end_m in candidates:
                    # Check gap with already placed sessions
                    if placed:
                        min_gap_ok = all(abs((day_date - p[0]).days) > gap_days for p in placed)
                        if not min_gap_ok:
                            continue

                    slot_key = (day_date, slot_h, slot_m, week_num)

                    # Check capacity
                    if len(slots[slot_key]['reps']) >= max_per_slot:
                        continue

                    # Check one-manager-per-slot
                    if one_manager_per_slot and manager in slots[slot_key]['managers']:
                        continue

                    # Found a valid slot
                    best_slot = (day_date, slot_h, slot_m, slot_end_h, slot_end_m)
                    break

                if best_slot:
                    day_date, slot_h, slot_m, slot_end_h, slot_end_m = best_slot
                    slot_key = (day_date, slot_h, slot_m, week_num)

                    # Place the session
                    session = {
                        'workday_id': wd_id,
                        'pseudo_name': name,
                        'email': rep['email'],
                        'manager': manager,
                        'role': role,
                        'shift_time': shift,
                        'off_day': rep['off_day'],
                        'schedule_day': day_date.strftime('%A'),
                        'schedule_date': day_date,
                        'session_start_time': f"{slot_h:02d}:{slot_m:02d}",
                        'session_end_time': f"{slot_end_h:02d}:{slot_end_m:02d}",
                        'week': week_num
                    }
                    scheduled.append(session)
                    placed.append((day_date, slot_h, slot_m))

                    slots[slot_key]['reps'].append(name)
                    slots[slot_key]['managers'].add(manager)
                else:
                    # Couldn't place this session
                    pass

            # Check if fully scheduled
            if len(placed) < sessions_per_rep:
                reason = "No free slot (capacity or gap constraint)" if placed else "No free slot"
                unscheduled.append((rep, len(placed), reason, week_num))

    return {
        'scheduled': scheduled,
        'unscheduled': unscheduled,
        'slots_grid': {}  # Could be populated for calendar view if needed
    }
