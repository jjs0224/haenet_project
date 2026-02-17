import React, { useState } from "react";
import { MenuAssistantAPI } from "../../api/menuAssistantApi";
import { MenuAPI } from "../../api/menuApi";

export default function MenuAssistant() {
    const [file, setFile] = useState(null);
    const [userProfileText, setUserProfileText] = useState(
        '{\n  "allergy_tags": []\n}',
    );
    const [runStep4, setRunStep4] = useState(true);
    const [runStep5, setRunStep5] = useState(true);
    const [runStep6, setRunStep6] = useState(true);

    const [enqueueResult, setEnqueueResult] = useState(null);
    const [error, setError] = useState("");

    const [jobId, setJobId] = useState("");
    const [jobStatus, setJobStatus] = useState(null);
    const [jobError, setJobError] = useState("");

    const onEnqueue = async () => {
        setError("");
        setEnqueueResult(null);
        setJobStatus(null);

        if (!file) {
            setError("image file is required");
            return;
        }

        let userProfile = null;
        if (userProfileText.trim()) {
            try {
                userProfile = JSON.parse(userProfileText);
            } catch (e) {
                setError("user_profile_json is invalid JSON");
                return;
            }
        }

        try {
            const res = await MenuAssistantAPI.enqueue({
                file,
                userProfile,
                runStep4,
                runStep5,
                runStep6,
            });
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
            const res = await MenuAPI.getMenuJob(jobId);
            setJobStatus(res.data);
        } catch (e) {
            setJobError(e?.response?.data?.detail || "job status fetch failed");
        }
    };

    return (
        <div style={{ padding: 16, maxWidth: 720 }}>
            <h2>Menu Assistant</h2>

            <div style={{ display: "grid", gap: 10 }}>
                <input
                    type="file"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                />

                <textarea
                    rows={6}
                    value={userProfileText}
                    onChange={(e) => setUserProfileText(e.target.value)}
                    placeholder="user_profile_json"
                />

                <label>
                    <input
                        type="checkbox"
                        checked={runStep4}
                        onChange={(e) => setRunStep4(e.target.checked)}
                    />
                    run_step4
                </label>
                <label>
                    <input
                        type="checkbox"
                        checked={runStep5}
                        onChange={(e) => setRunStep5(e.target.checked)}
                    />
                    run_step5
                </label>
                <label>
                    <input
                        type="checkbox"
                        checked={runStep6}
                        onChange={(e) => setRunStep6(e.target.checked)}
                    />
                    run_step6
                </label>

                <button onClick={onEnqueue}>
                    Enqueue menu_assistant_pipeline
                </button>
            </div>

            {error && <div className="errorBox">{error}</div>}
            {enqueueResult && (
                <pre className="card">
                    {JSON.stringify(enqueueResult, null, 2)}
                </pre>
            )}

            <hr style={{ margin: "24px 0" }} />

            <h3>Job Status</h3>
            <div style={{ display: "grid", gap: 10 }}>
                <input
                    value={jobId}
                    onChange={(e) => setJobId(e.target.value)}
                    placeholder="job_id"
                />
                <button onClick={onFetchStatus}>/jobs/{"{id}"} ��ȸ</button>
            </div>
            {jobError && <div className="errorBox">{jobError}</div>}
            {jobStatus && (
                <pre className="card">{JSON.stringify(jobStatus, null, 2)}</pre>
            )}
        </div>
    );
}
