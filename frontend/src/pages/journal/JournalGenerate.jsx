import React, { useState } from "react";
import { JournalAPI } from "../../api/journalApi";
import { JobAPI } from "../../api/jobApi";
import {
  buildDefaultJournalPayload,
  normalizeJournalPayload,
  validateJournalPayload,
} from "../../types/journal";

export default function JournalGenerate() {
  const [payload, setPayload] = useState(buildDefaultJournalPayload());
  const [dislikeTagsText, setDislikeTagsText] = useState("");
  const [itemIdsText, setItemIdsText] = useState("");

  const [enqueueResult, setEnqueueResult] = useState(null);
  const [error, setError] = useState("");

  const [jobId, setJobId] = useState("");
  const [jobStatus, setJobStatus] = useState(null);
  const [jobError, setJobError] = useState("");

  const updateMember = (field, value) => {
    setPayload((prev) => ({
      ...prev,
      member: { ...prev.member, [field]: value },
    }));
  };

  const updateReview = (idx, field, value) => {
    setPayload((prev) => {
      const nextReviews = prev.reviews.map((r, i) =>
        i === idx ? { ...r, [field]: value } : r
      );
      return { ...prev, reviews: nextReviews };
    });
  };

  const onEnqueue = async () => {
    setError("");
    setEnqueueResult(null);
    setJobStatus(null);

    const normalized = normalizeJournalPayload(payload);

    const dislikeTags = dislikeTagsText
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const itemIds = itemIdsText
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
      .map((t) => Number(t))
      .filter((n) => !Number.isNaN(n));

    normalized.member.dislike_tags = dislikeTags;
    normalized.member.item_ids = itemIds;

    const errors = validateJournalPayload(normalized);
    if (errors.length) {
      setError(errors.join("\n"));
      return;
    }

    try {
      const res = await JournalAPI.enqueue(normalized);
      setEnqueueResult(res.data);
      if (res.data?.job_id) {
        setJobId(res.data.job_id);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || "enqueue failed");
    }
  };

  const onFetchStatus = async () => {
    setJobError("");
    setJobStatus(null);
    if (!jobId) {
      setJobError("job_id is required");
      return;
    }

    try {
      const res = await JobAPI.get(jobId);
      setJobStatus(res.data);
    } catch (e) {
      setJobError(e?.response?.data?.detail || "job status fetch failed");
    }
  };

  return (
    <div style={{ padding: 16, maxWidth: 720 }}>
      <h2>Journal Generate</h2>

      <div style={{ display: "grid", gap: 10 }}>
        <label>
          journal_type
          <select
            value={payload.journal_type}
            onChange={(e) => setPayload((prev) => ({ ...prev, journal_type: e.target.value }))}
          >
            <option value="journal">journal</option>
            <option value="culture">culture</option>
          </select>
        </label>

        <label>
          template.language
          <input
            value={payload.template.language}
            onChange={(e) =>
              setPayload((prev) => ({
                ...prev,
                template: { ...prev.template, language: e.target.value },
              }))
            }
          />
        </label>

        <label>
          member.nickname
          <input
            value={payload.member.nickname}
            onChange={(e) => updateMember("nickname", e.target.value)}
          />
        </label>
        <label>
          member.gender
          <input value={payload.member.gender} onChange={(e) => updateMember("gender", e.target.value)} />
        </label>
        <label>
          member.country
          <input value={payload.member.country} onChange={(e) => updateMember("country", e.target.value)} />
        </label>
        <label>
          member.dislike_tags (comma)
          <input value={dislikeTagsText} onChange={(e) => setDislikeTagsText(e.target.value)} />
        </label>
        <label>
          member.item_ids (comma)
          <input value={itemIdsText} onChange={(e) => setItemIdsText(e.target.value)} />
        </label>

        <div>
          <h4>Reviews (3 items)</h4>
          {payload.reviews.map((r, idx) => (
            <div key={idx} style={{ display: "grid", gap: 6, marginBottom: 10 }}>
              <input
                placeholder={`reviews[${idx}].review_title`}
                value={r.review_title}
                onChange={(e) => updateReview(idx, "review_title", e.target.value)}
              />
              <textarea
                rows={3}
                placeholder={`reviews[${idx}].review_content`}
                value={r.review_content}
                onChange={(e) => updateReview(idx, "review_content", e.target.value)}
              />
            </div>
          ))}
        </div>

        <button onClick={onEnqueue}>Enqueue journal_generate</button>
      </div>

      {error && (
        <pre className="errorBox" style={{ whiteSpace: "pre-wrap" }}>
          {error}
        </pre>
      )}
      {enqueueResult && <pre className="card">{JSON.stringify(enqueueResult, null, 2)}</pre>}

      <hr style={{ margin: "24px 0" }} />

      <h3>Job Status</h3>
      <div style={{ display: "grid", gap: 10 }}>
        <input
          value={jobId}
          onChange={(e) => setJobId(e.target.value)}
          placeholder="job_id"
        />
        <button onClick={onFetchStatus}>/jobs/{"{id}"} Á¶È¸</button>
      </div>
      {jobError && <div className="errorBox">{jobError}</div>}
      {jobStatus && <pre className="card">{JSON.stringify(jobStatus, null, 2)}</pre>}
    </div>
  );
}
