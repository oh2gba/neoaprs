// The Bulletins tab: the message board in its sections, and the box to post to it.
export const bulletins = {
  "bulletins.section.announcement": "Announcements",
  "bulletins.section.bulletin": "Bulletins",
  "bulletins.section.group": "Group messages",
  "bulletins.section.nws": "Weather service",

  "bulletins.empty": "Nothing on the board.",
  "bulletins.about_label": "About bulletins",
  "bulletins.about1": "A bulletin is a message to everyone, shown on every station's board.",
  "bulletins.about2": "Use it for net times, events, warnings.",
  "bulletins.delete_title": "Delete (stop sending)",
  "bulletins.delete_own": "Delete our bulletin {slot}",
  "bulletins.delete": "Delete the bulletin {slot} from {sender}",
  "bulletins.to": "to",
  "bulletins.ours": "ours",
  "bulletins.posted": "posted {time}",
  "bulletins.heard_title": "first heard {first}, last heard {last}",
  "bulletins.heard": { "=1": "heard once, {span} ago", other: "heard {n} times, {span} ago" },

  "bulletins.post_label": "Post a bulletin",
  "bulletins.kind": "Kind",
  "bulletins.kind_name.bulletin": "Bulletin",
  "bulletins.kind_name.announcement": "Announcement",
  "bulletins.kind_name.group": "Group bulletin",
  "bulletins.sent_for": "Sent for",
  "bulletins.group": "Group",
  "bulletins.group_placeholder": "Name",
  "bulletins.text": "Text",
  "bulletins.tip.hours": { one: "{n} hour", other: "{n} hours" },
  "bulletins.tip.days": { one: "{n} day", other: "{n} days" },
  "bulletins.tip.kinds1":
    "A bulletin and an announcement are shown by every station that hears them: a bulletin for what matters now, an announcement for what stays true for days.",
  "bulletins.tip.kinds2":
    "A group bulletin is for one group; every station shows it unless its operator picked other groups to show.",
  "bulletins.tip.sent_for": "How long the post is repeated, counted from its first packet.",
  "bulletins.tip.group1":
    "The name is part of the address, as in BLN3HAMS, so every station hears the bulletin and shows it, unless its operator picked other groups to show.",
  "bulletins.tip.group2": "NeoAPRS shows the bulletins of every group it hears, under Group messages.",
  "bulletins.tip.text1": "Up to {max} characters, printable, none of {forbidden}.",
  "bulletins.tip.text_repeat": "It goes out in one radio packet, repeated for the time chosen under Sent for.",
  "bulletins.post": "Post",
} as const;
