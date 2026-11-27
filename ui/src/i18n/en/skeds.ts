// The HF tests tab (the keys say skeds): the board of tests planned on the air on HF, and the box to plan one. A test here is a planned test on the air between stations, not the Tune or Test of Settings.
export const skeds = {
  "skeds.about_label": "About HF tests",
  "skeds.about1":
    "For stations trying APRS on HF: say when you will be on the air and on which frequency, so that another station can test with you.",
  "skeds.about2": "The board is public, on neo.oh2gba.eu. It is not sent by radio.",

  "skeds.empty": "No tests planned.",
  "skeds.past_title": "Past tests",
  "skeds.past_empty": "No past tests.",
  "skeds.when": "{from} to {to} UTC",
  "skeds.local": "Your time: {from} to {to}",
  "skeds.ours": "ours",
  "skeds.join": "Join",
  "skeds.join_title": "Plan a test of yours at the same time on the same frequency",
  "skeds.join_label": "Join the test of {calls}, {when}",
  "skeds.delete_title": "Delete (take it off the board)",
  "skeds.delete_label": "Delete our test, {when}",

  "skeds.post_label": "Plan a test",
  "skeds.day": "Day",
  "skeds.time": "Time (UTC)",
  "skeds.from": "From",
  "skeds.to": "To",
  "skeds.until": "to",
  "skeds.frequency": "Frequency",
  "skeds.frequency_other": "Other",
  "skeds.dial": "Dial",
  "skeds.note": "Note",
  "skeds.post": "Post on neo.oh2gba.eu",
} as const;
