/**
 * Google Apps Script — Personal -> Band Calendar Sync
 *
 * What it does
 * - Mirrors events from SOURCE_ID (your personal calendar) to TARGET_ID (band calendar)
 * - Tracks mirrored events via a marker in the description: [SRC:<seriesId>|<startMs>]
 * - Updates title/location/time/description if changed; deletes mirrored events removed from source
 * - Handles all-day vs timed events and recurring event instances
 *
 * Permissions
 * - Run this script in the account that can READ the source and WRITE to the target
 *   Option A: Run under your personal account; share the band calendar with your personal account (Make changes)
 *   Option B: Run under the band account; share your personal calendar with the band account (See all details)
 *
 * Setup
 * 1) Fill SOURCE_ID and TARGET_ID below. Calendar IDs are in Google Calendar > Settings > Integrate calendar.
 *    - Personal calendars are usually your email (e.g., you@gmail.com)
 *    - Band calendar typically ends with @group.calendar.google.com
 * 2) Run sync() once to authorize.
 * 3) Add a time-driven trigger (e.g., every 15 minutes).
 *
 * Optional filtering
 * - If COPY_ONLY_TAGGED is true, only events whose title contains FILTER_TAG (e.g., "#band") are mirrored.
 */
//  https://script.google.com
//https://script.google.com/macros/s/AKfycbz1ojl37HyZq86-4b21LbesL3780FurIOgb86xFDP5jp33_dyTcOSS7gZZhq1u7BiMd-w/exec

const SOURCE_ID = 'ty.drake.music@gmail.com';
const SOURCE_ID_DRUMMER = 'blade.wolling@gmail.com';
const SOURCE_ID_KEYS = 'mannjm53@gmail.com'; // Jim Mann (keys)
const TARGET_ID = '3b522cd816670ae9f2d68d25e743eaa0b0df7dac19ef0c90a4f1ce701913ace9@group.calendar.google.com';

const WINDOW_PAST_DAYS = 7;     // also sync slight past for edits/deletes
const WINDOW_FUTURE_DAYS = 180; // lookahead window
const COPY_ONLY_TAGGED = false; // set true to filter by tag
const FILTER_TAG = '#band';
// Visible tagging so band knows whose personal item it is
const OWNER_NAME = 'Tyler';              // kept for backward compatibility (unused in multi-source)
const OWNER_TAG = '[Tyler]';             // kept for backward compatibility (unused in multi-source)
const TAG_POSITION = 'prefix';           // 'prefix' or 'suffix'
const SHOW_SOURCE_NOTE = true;           // add a one-line note in description

// Multi-source configuration (add more sources as needed)
const SOURCES = [
  { id: SOURCE_ID,          ownerName: 'Tyler', ownerTag: '[Tyler]', color: CalendarApp.EventColor.PALE_RED },
  { id: SOURCE_ID_DRUMMER,  ownerName: 'Wade',  ownerTag: '[Wade]',  color: CalendarApp.EventColor.PALE_BLUE },
  { id: SOURCE_ID_KEYS,     ownerName: 'Jim',   ownerTag: '[Jim]',   color: CalendarApp.EventColor.PALE_GREEN },
];

function sync() {
  const now = new Date();
  const start = new Date(now.getTime() - WINDOW_PAST_DAYS * 24 * 3600 * 1000);
  const end = new Date(now.getTime() + WINDOW_FUTURE_DAYS * 24 * 3600 * 1000);
  const tgtCal = CalendarApp.getCalendarById(TARGET_ID);
  if (!tgtCal) throw new Error('Target calendar not found: ' + TARGET_ID);
  const tgtEvents = tgtCal.getEvents(start, end);

  // Build index of target events by source marker
  const tgtByMarker = {};
  tgtEvents.forEach(e => {
    const m = markerFromDescription(e.getDescription());
    if (m) tgtByMarker[m] = e;
  });

  const keepMarkers = new Set();

  // Iterate each configured source calendar
  SOURCES.forEach(src => {
    const srcCal = CalendarApp.getCalendarById(src.id);
    if (!srcCal) {
      // Skip unknown sources but keep syncing others
      Logger.log('Source calendar not found: ' + src.id);
      return;
    }

    const srcEvents = srcCal.getEvents(start, end);

    srcEvents.forEach(se => {
      // Optional filter by tag in title
      if (COPY_ONLY_TAGGED && !titleHasTag(se.getTitle())) return;

      const marker = buildMarker(se);
      keepMarkers.add(marker);

      const summary = se.getTitle();
      const targetTitle = applyTitleTag(summary, src.ownerTag);
      const location = se.getLocation() || '';
      const srcDesc = se.getDescription() || '';
      const baseDesc = SHOW_SOURCE_NOTE ? ensureSourceNote(srcDesc, src.ownerName) : srcDesc;
      const description = ensureMarker(baseDesc, marker);

      const existing = tgtByMarker[marker];

      if (!existing) {
        // Create new
        if (se.isAllDayEvent()) {
          const s = stripDate(se.getAllDayStartDate());
          const eEx = stripDate(se.getEndTime()); // end date is exclusive for all-day
          const created = tgtCal.createAllDayEvent(targetTitle, s, { description, location });
          safeSetAllDayDates(created, s, eEx);
          setEventColorSafe(created, src.color);
        } else {
          const created = tgtCal.createEvent(targetTitle, se.getStartTime(), se.getEndTime(), { description, location });
          setEventColorSafe(created, src.color);
        }
        return;
      }

      // If all-day status changed, recreate to switch type
      if (existing.isAllDayEvent() !== se.isAllDayEvent()) {
        existing.deleteEvent();
        if (se.isAllDayEvent()) {
          const s = stripDate(se.getAllDayStartDate());
          const eEx = stripDate(se.getEndTime());
          const recreated = tgtCal.createAllDayEvent(targetTitle, s, { description, location });
          safeSetAllDayDates(recreated, s, eEx);
          setEventColorSafe(recreated, src.color);
        } else {
          const recreated = tgtCal.createEvent(targetTitle, se.getStartTime(), se.getEndTime(), { description, location });
          setEventColorSafe(recreated, src.color);
        }
        return;
      }

      // Update fields when different
      if (existing.getTitle() !== targetTitle) existing.setTitle(targetTitle);
      if (existing.getLocation() !== location) existing.setLocation(location);
      const curDesc = existing.getDescription() || '';
      if (curDesc !== description) existing.setDescription(description);

      if (!se.isAllDayEvent()) {
        if (existing.getStartTime().getTime() !== se.getStartTime().getTime() ||
            existing.getEndTime().getTime() !== se.getEndTime().getTime()) {
          existing.setTime(se.getStartTime(), se.getEndTime());
        }
      } else {
        // Keep multi-day all-day span in sync
        const s = stripDate(se.getAllDayStartDate());
        const eEx = stripDate(se.getEndTime());
        const curS = stripDate(existing.getAllDayStartDate());
        const curEEx = stripDate(existing.getEndTime());
        if (curS.getTime() !== s.getTime() || curEEx.getTime() !== eEx.getTime()) {
          safeSetAllDayDates(existing, s, eEx);
        }
      }
      setEventColorSafe(existing, src.color);
    });
  });

  // Delete mirrored target events that no longer exist in source window
  Object.entries(tgtByMarker).forEach(([marker, te]) => {
    if (!keepMarkers.has(marker)) te.deleteEvent();
  });
}

// Helpers
function buildMarker(e) {
  const seriesId = e.getId();
  // Use start time to distinguish instances of recurring events
  const startMs = e.isAllDayEvent() ? e.getAllDayStartDate().getTime() : e.getStartTime().getTime();
  return `[SRC:${seriesId}|${startMs}]`;
}

function markerFromDescription(desc) {
  if (!desc) return null;
  const m = desc.match(/\[SRC:([^\]]+)\]/);
  return m ? m[0] : null;
}

function ensureMarker(desc, marker) {
  if (!desc) return marker;
  return desc.includes(marker) ? desc : `${desc}\n${marker}`;
}

function titleHasTag(title) {
  return (title || '').toLowerCase().includes(FILTER_TAG.toLowerCase());
}

// Apply a visible owner tag to the event title without duplicating it
function applyTitleTag(title, ownerTag) {
  const t = title || '';
  const tag = ownerTag || OWNER_TAG;
  if (!tag) return t;
  if (t.includes(tag)) return t; // already tagged anywhere in title
  return TAG_POSITION === 'suffix' ? `${t} ${tag}` : `${tag} ${t}`;
}

// Add a one-line source note to the description (idempotent)
function ensureSourceNote(desc, ownerName) {
  const name = ownerName || OWNER_NAME;
  const note = `Source: ${name} (personal calendar)`;
  const d = desc || '';
  if (!SHOW_SOURCE_NOTE) return d;
  return d.includes(note) ? d : (d ? `${d}\n${note}` : note);
}

// Normalize a Date to midnight (local) for consistent all-day comparisons
function stripDate(d) {
  const nd = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  return nd;
}

// Safely apply an all-day date range; use advanced API when available, else recreate
function safeSetAllDayDates(event, startDate, endExclusiveDate) {
  try {
    // Apps Script's CalendarApp Event has setAllDayDates in many environments
    if (typeof event.setAllDayDates === 'function') {
      event.setAllDayDates(startDate, endExclusiveDate);
      return;
    }
  } catch (e) {
    // fall through to recreation
  }
  try {
    // Fallback: delete and recreate to enforce span (kept minimal; caller can handle if needed)
    const cal = event.getOriginalCalendar();
    const title = event.getTitle();
    const loc = event.getLocation();
    const desc = event.getDescription();
    event.deleteEvent();
    const created = cal.createAllDayEvent(title, startDate, { description: desc, location: loc });
    if (typeof created.setAllDayDates === 'function') created.setAllDayDates(startDate, endExclusiveDate);
  } catch (err) {
    // As a last resort, leave as is to avoid data loss
  }
}

// Set a color on the event if supported
function setEventColorSafe(event, color) {
  if (!event || !color) return;
  try {
    event.setColor(color);
  } catch (e) {
    // Ignore if color setting is not supported or perms are missing
  }
}
