export const JOURNAL_TYPES = ["journal", "culture"];

export function buildDefaultJournalPayload() {
  return {
    journal_type: "journal",
    template: {
      language: "en",
      style: {},
    },
    member: {
      nickname: "",
      gender: "",
      country: "",
      dislike_tags: [],
      item_ids: [],
    },
    reviews: [
      { review_title: "", review_content: "" },
      { review_title: "", review_content: "" },
      { review_title: "", review_content: "" },
    ],
  };
}

export function normalizeJournalPayload(payload) {
  const next = JSON.parse(JSON.stringify(payload || {}));

  if (!next.template) next.template = { language: "en", style: {} };
  if (!next.template.language) next.template.language = "en";
  if (!next.template.style) next.template.style = {};

  if (!next.member) next.member = {};
  if (!Array.isArray(next.member.dislike_tags)) next.member.dislike_tags = [];
  if (!Array.isArray(next.member.item_ids)) next.member.item_ids = [];

  if (!Array.isArray(next.reviews)) next.reviews = [];
  while (next.reviews.length < 3) {
    next.reviews.push({ review_title: "", review_content: "" });
  }
  next.reviews = next.reviews.slice(0, 3);

  return next;
}

export function validateJournalPayload(payload) {
  const errors = [];
  if (!payload) {
    return ["payload is required"];
  }
  if (!JOURNAL_TYPES.includes(payload.journal_type)) {
    errors.push("journal_type must be 'journal' or 'culture'");
  }
  if (!payload.template || !payload.template.language) {
    errors.push("template.language is required");
  }
  if (!payload.member || !payload.member.nickname) {
    errors.push("member.nickname is required");
  }
  if (!Array.isArray(payload.reviews) || payload.reviews.length !== 3) {
    errors.push("reviews must contain exactly 3 items");
  } else {
    payload.reviews.forEach((r, idx) => {
      if (!r.review_title) errors.push(`reviews[${idx}].review_title is required`);
      if (!r.review_content) errors.push(`reviews[${idx}].review_content is required`);
    });
  }
  return errors;
}
