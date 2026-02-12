import React, { useContext, useEffect, useMemo, useState } from "react";
import { RestrictionsAdminAPI } from "../../api/restrictionsAdminApi";
import { MetaContext } from "../../context/MetaContext";
import RestrictionsBatchCreate from "./RestrictionsBatchCreate";
import RestrictionsAdminList from "./RestrictionsAdminList";

//  어떤 형태로 와도 "배열"만 뽑아내는 정규화
function normalizeRestrictions(resOrPayload) {
  // axios response면 resOrPayload.data가 payload
  const payload = resOrPayload?.data ?? resOrPayload;

  // only_active=1 케이스: payload 자체가 배열
  if (Array.isArray(payload)) return payload;

  // only_active=0 케이스: { etag, data:[...] }
  if (Array.isArray(payload?.data)) return payload.data;

  // 혹시 { data:{ data:[...] } }
  if (Array.isArray(payload?.data?.data)) return payload.data.data;

  // 혹시 { categories:[...] }
  if (Array.isArray(payload?.categories)) return payload.categories;

  return [];
}

export default function RestrictionsAdminContainer() {
  const { metaActions } = useContext(MetaContext);

  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [data, setData] = useState([]);
  const [q, setQ] = useState("");

  const loadAll = async () => {
    setMsg("");
    setLoading(true);
    try {
      const res = await RestrictionsAdminAPI.list({ onlyActive: false });

      const list = normalizeRestrictions(res);
      setData(list);
      setMsg(` 조회 완료 (${list.length})`);

      //  콘솔로도 확인
      console.log("[ADMIN] raw payload =", res?.data ?? res);
      console.log("[ADMIN] parsed list length =", list.length);
    } catch (e) {
      setMsg(`❌ ${e?.response?.data?.detail || e?.message || "조회 실패"}`);
      setData([]);
      console.error("[ADMIN] list error:", e?.response?.data || e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateCategoryLocal = (category_id, patch) => {
    setData((prev) => prev.map((c) => (c.category_id === category_id ? { ...c, ...patch } : c)));
  };

  const updateItemLocal = (category_id, item_id, patch) => {
    setData((prev) =>
      prev.map((c) => {
        if (c.category_id !== category_id) return c;
        return {
          ...c,
          items: (c.items || []).map((it) => (it.item_id === item_id ? { ...it, ...patch } : it)),
        };
      })
    );
  };

  const saveCategory = async (c) => {
    setMsg("");
    try {
      await RestrictionsAdminAPI.updateCategory(c.category_id, {
        category_label_ko: c.category_label_ko,
        category_label_en: c.category_label_en,
        category_active: !!c.category_active,
      });

      // metaActions가 없거나 refresh가 없으면 여기서 터질 수 있어서 방어
      if (metaActions?.refresh) await metaActions.refresh({ force: true });

      await loadAll();
      setMsg(` 카테고리 저장 완료 (${c.category_id})`);
    } catch (e) {
      setMsg(`❌ ${e?.response?.data?.detail || e?.message || "카테고리 저장 실패"}`);
    }
  };

  const saveItem = async (_, it) => {
    setMsg("");
    try {
      await RestrictionsAdminAPI.updateItem(it.item_id, {
        item_label_ko: it.item_label_ko,
        item_label_en: it.item_label_en,
        item_active: !!it.item_active,
      });

      if (metaActions?.refresh) await metaActions.refresh({ force: true });

      await loadAll();
      setMsg(` 아이템 저장 완료 (${it.item_id})`);
    } catch (e) {
      setMsg(`❌ ${e?.response?.data?.detail || e?.message || "아이템 저장 실패"}`);
    }
  };

  const addItemToCategory = async (category_id, payload) => {
    setMsg("");
    try {
      await RestrictionsAdminAPI.addItemToCategory(category_id, {
        item_label_ko: payload.item_label_ko,
        item_label_en: payload.item_label_en,
        item_active: true,
      });

      if (metaActions?.refresh) await metaActions.refresh({ force: true });

      await loadAll();
      setMsg(` 아이템 추가 완료 (Category #${category_id})`);
    } catch (e) {
      setMsg(`❌ ${e?.response?.data?.detail || e?.message || "아이템 추가 실패"}`);
    }
  };

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return data;
    const match = (s) => (s ?? "").toString().toLowerCase().includes(needle);

    return (data || [])
      .map((c) => {
        const catHit = match(c.category_label_ko) || match(c.category_label_en);
        if (catHit) return c;
        const items = (c.items || []).filter((it) => match(it.item_label_ko) || match(it.item_label_en));
        return { ...c, items };
      })
      .filter((c) => (c.items || []).length > 0 || match(c.category_label_ko) || match(c.category_label_en));
  }, [data, q]);

  return (
    <div className="restrictions-admin-wrapper">
      <div className="restrictions-toolbar">
        <button onClick={loadAll} disabled={loading}>
          {loading ? "로딩..." : "새로고침"}
        </button>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="검색 (카테고리/아이템)"
        />
      </div>

      {msg && <div className="admin-message">{msg}</div>}

      {/*  여기서 바로 판별 가능: 파싱이 0인지/렌더링 문제인지 */}
{/*       <div style={{ marginBottom: 12, padding: 10, background: "#fafafa", border: "1px solid #eee" }}> */}
{/*         <div><b>DEBUG</b> parsed length: {filtered.length}</div> */}
{/*         <details style={{ marginTop: 6 }}> */}
{/*           <summary>raw payload 보기</summary> */}
{/*           <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(raw, null, 2)}</pre> */}
{/*         </details> */}
{/*       </div> */}

      <div className="admin-grid-layout">
        <RestrictionsBatchCreate
          onSaved={async () => {
            if (metaActions?.refresh) await metaActions.refresh({ force: true });
            await loadAll();
          }}
        />

        <RestrictionsAdminList
          data={filtered}
          loading={loading}
          onChangeCategory={updateCategoryLocal}
          onChangeItem={updateItemLocal}
          onSaveCategory={saveCategory}
          onSaveItem={saveItem}
          onAddItem={addItemToCategory}
        />
      </div>
    </div>
  );
}
