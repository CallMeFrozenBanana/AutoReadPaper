import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpen,
  Library,
  Radio,
  Settings,
  Activity,
  Plus,
  Search,
  ArrowUpRight,
  ArrowLeft,
  Upload,
  FileText,
  Star,
  ChevronRight,
  X,
  Play,
  Pause,
  Power,
  Check,
  Clock,
  RefreshCw,
  Download,
  FolderOpen,
  SlidersHorizontal,
  Globe,
  Layers,
  CheckCircle2,
  AlertCircle,
  Trash2,
} from "lucide-react";
import "./style.css";

type Obj = Record<string, any>;
const labels: Obj = {
  metadata_only: "仅元数据",
  extracted: "全文已解析",
  abstract_only: "摘要速览",
  partial_fulltext: "部分全文总结",
  fulltext: "全文总结",
  queued: "排队中",
  running: "运行中",
  succeeded: "已完成",
  blocked: "等待条件",
  retry_wait: "等待重试",
  failed: "失败",
  cancelled: "已取消",
};
const stamp = (s: string) =>
  s
    ? new Date(s).toLocaleString("zh-CN", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
async function api(path: string, method = "GET", body?: any) {
  const r = await fetch("/api" + path, {
    method,
    headers:
      body instanceof FormData
        ? undefined
        : { "Content-Type": "application/json" },
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((x: Obj) => x.msg).join("；")
      : data.detail;
    throw new Error(detail || "请求失败");
  }
  return data;
}
const asset = (p: string) => "/api/assets/" + p;
function Pill({ value }: { value: string }) {
  return <span className={"pill " + value}>{labels[value] || value}</span>;
}
function Empty({
  icon: Icon = BookOpen,
  title,
  children,
  action,
}: {
  icon?: any;
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={30} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
function MultiSelect({
  value,
  onChange,
  options,
  label,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  options: Obj;
  label: string;
}) {
  const [q, setQ] = useState("");
  return (
    <details className="multiselect">
      <summary>
        {value.length ? value.map((v) => options[v] || v).join("、") : label}
      </summary>
      <div className="select-pop">
        <input
          aria-label="搜索选项"
          placeholder="搜索选项…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {Object.entries(options)
          .filter(([k, v]) => (k + v).toLowerCase().includes(q.toLowerCase()))
          .map(([k, v]) => (
            <label key={k}>
              <input
                type="checkbox"
                checked={value.includes(k)}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...value, k]
                      : value.filter((x) => x !== k),
                  )
                }
              />
              {String(v)} <small>{k}</small>
            </label>
          ))}
      </div>
    </details>
  );
}
function TopicAction({
  hint,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { hint: string }) {
  const hintId = React.useId();
  return (
    <span className="topic-action">
      <button {...props} aria-describedby={hintId}>
        {children}
      </button>
      <span className="action-tooltip" id={hintId} role="tooltip">
        {hint}
      </span>
    </span>
  );
}

function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const dialog = React.useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const focusable = () =>
      Array.from(
        dialog.current?.querySelectorAll<HTMLElement>(
          "button,input,select,textarea,summary,a[href]",
        ) || [],
      ).filter(
        (el) =>
          el.getClientRects().length && !(el as HTMLButtonElement).disabled,
      );
    focusable()[0]?.focus();
    const f = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const list = focusable();
        if (e.shiftKey && document.activeElement === list[0]) {
          e.preventDefault();
          list.at(-1)?.focus();
        } else if (!e.shiftKey && document.activeElement === list.at(-1)) {
          e.preventDefault();
          list[0]?.focus();
        }
      }
    };
    document.addEventListener("keydown", f);
    return () => {
      document.removeEventListener("keydown", f);
      previous?.focus();
    };
  }, []);
  return (
    <div className="overlay" onClick={onClose}>
      <section
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={"modal " + (wide ? "wide" : "")}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <div>
            <span className="eyebrow">AUTOREADPAPER</span>
            <h2>{title}</h2>
          </div>
          <button className="icon-btn" aria-label="关闭" onClick={onClose}>
            <X />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
function CleanupModal({
  topics,
  onClose,
  onSaved,
  notify,
}: {
  topics: Obj[];
  onClose: () => void;
  onSaved: () => void;
  notify: (s: string) => void;
}) {
  const [filters, setFilters] = useState<Obj>({
    mode: "unprocessed",
    topic_id: "",
    older_days: 0,
    score_below: 60,
    protect_favorites: true,
    protect_notes: true,
  });
  const [plan, setPlan] = useState<Obj | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function change(key: string, value: any) {
    setFilters((v) => ({ ...v, [key]: value }));
    setPlan(null);
    setSelected([]);
    setConfirmation("");
    setError("");
  }
  async function preview() {
    setBusy(true);
    setError("");
    setPlan(null);
    setConfirmation("");
    try {
      const r = await api("/library/cleanup/preview", "POST", filters);
      setPlan(r);
      setSelected(r.items.map((p: Obj) => p.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      const r = await api("/library/cleanup/commit", "POST", {
        token: plan.token,
        paper_ids: selected,
        confirmation,
      });
      notify(
        r.message +
          (r.file_cleanup_pending.length
            ? "；部分文件暂未移除，重启服务后重试"
            : ""),
      );
      onSaved();
      onClose();
    } catch (e) {
      setError((e as Error).message);
      setConfirmation("");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="清理论文库" onClose={onClose} wide>
      <p className="muted">
        先预览，再勾选确认。删除会移除论文、全部版本、报告、评分、笔记及原文文件，无法撤销。主题配置保留。单独导出的文件不会删除，后续检索仍可能重新发现这些论文。
      </p>
      <fieldset className="cleanup-controls" disabled={busy}>
        <Field label="清理范围">
          <select
            value={filters.mode}
            onChange={(e) => change("mode", e.target.value)}
          >
            <option value="unprocessed">未生成阅读报告的论文</option>
            <option value="read">已读论文</option>
            <option value="low_score">低阅读优先分论文</option>
            <option value="all">全部论文（仍按保护条件筛选）</option>
          </select>
        </Field>
        <Field label="限定主题">
          <select
            value={filters.topic_id}
            onChange={(e) => change("topic_id", e.target.value)}
          >
            <option value="">全部主题</option>
            {topics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="入库时间">
          <select
            value={filters.older_days}
            onChange={(e) => change("older_days", +e.target.value)}
          >
            {[0, 7, 30, 90, 180, 365].map((d) => (
              <option key={d} value={d}>
                {d ? d + " 天以前入库" : "不限时间"}
              </option>
            ))}
          </select>
        </Field>
        {filters.mode === "low_score" && (
          <Field label="阅读优先分低于">
            <select
              value={filters.score_below}
              onChange={(e) => change("score_below", +e.target.value)}
            >
              {[40, 50, 60, 70, 80].map((n) => (
                <option key={n} value={n}>
                  {n} 分
                </option>
              ))}
            </select>
          </Field>
        )}
        <label className="check-row">
          <input
            type="checkbox"
            checked={filters.protect_favorites}
            onChange={(e) => change("protect_favorites", e.target.checked)}
          />
          保留收藏论文
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={filters.protect_notes}
            onChange={(e) => change("protect_notes", e.target.checked)}
          />
          保留有笔记的论文
        </label>
      </fieldset>
      {filters.mode === "low_score" && (
        <p className="muted">
          只匹配有效评分；待评分论文不会被当作低分。全部主题下使用最高匹配主题分。限定主题会删除匹配论文在整个库中的记录，不只是解除主题关联。
        </p>
      )}
      <button className="btn secondary" disabled={busy} onClick={preview}>
        {busy ? "处理中…" : "预览待清理论文"}
      </button>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {plan && (
        <section className="cleanup-preview">
          <h3>
            匹配 {plan.count} 篇，已选 {selected.length} 篇
          </h3>
          <p className="muted">
            已保护 {plan.protected} 篇收藏或有笔记的论文。预览有效期 10
            分钟；期间数据发生变化会要求重新预览。
          </p>
          <button
            className="text-btn"
            disabled={busy}
            onClick={() => {
              setSelected(
                selected.length === plan.items.length
                  ? []
                  : plan.items.map((p: Obj) => p.id),
              );
              setConfirmation("");
            }}
          >
            {selected.length === plan.items.length ? "取消全选" : "全选"}
          </button>
          <div className="cleanup-list">
            {plan.items.map((p: Obj) => (
              <label className="cleanup-row" key={p.id}>
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={selected.includes(p.id)}
                  onChange={(e) => {
                    setSelected((v) =>
                      e.target.checked
                        ? [...v, p.id]
                        : v.filter((x) => x !== p.id),
                    );
                    setConfirmation("");
                  }}
                />
                <span>
                  {p.title}
                  <small>
                    {p.reports} 份报告
                    {p.priority_score != null
                      ? " · 优先分 " + p.priority_score
                      : ""}
                    {p.favorite ? " · 已收藏" : ""}
                    {p.has_notes ? " · 有笔记" : ""}
                  </small>
                </span>
              </label>
            ))}
          </div>
          {!!selected.length && (
            <>
              <Field label={"输入“删除 " + selected.length + " 篇”以确认"}>
                <input
                  aria-label="清理确认文字"
                  value={confirmation}
                  disabled={busy}
                  onChange={(e) => setConfirmation(e.target.value)}
                  placeholder={"删除 " + selected.length + " 篇"}
                />
              </Field>
              <button
                className="btn danger"
                disabled={
                  busy || confirmation !== "删除 " + selected.length + " 篇"
                }
                onClick={remove}
              >
                永久删除选中的 {selected.length} 篇论文
              </button>
            </>
          )}
        </section>
      )}
    </Modal>
  );
}

const defaults: Obj = {
  name: "",
  description: "",
  keywords: [],
  exclusions: [],
  questions: "",
  categories: [],
  query: "",
  frequency: "daily",
  time: "09:00",
  timezone: "Asia/Shanghai",
  weekday: 0,
  lookback_days: 30,
  date_from: "",
  date_to: "",
  daily_limit: 5,
  language: "zh",
  update_policy: "auto",
};
function TopicForm({
  initial,
  options,
  onClose,
  onSaved,
  notify,
}: {
  initial?: Obj;
  options: Obj;
  onClose: () => void;
  onSaved: () => void;
  notify: (s: string) => void;
}) {
  const [v, setV] = useState<Obj>(initial || { ...defaults });
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Obj | null>(null);
  const [error, setError] = useState("");
  const [preset, setPreset] = useState("");
  const [customBudget, setCustomBudget] = useState(
    initial ? ![1, 3, 5, 10, 20].includes(initial.daily_limit) : false,
  );
  const [customDate, setCustomDate] = useState(!!initial?.date_from);
  const update = (k: string, val: any) => setV((o) => ({ ...o, [k]: val }));
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(
        initial ? "/topics/" + initial.id : "/topics",
        initial ? "PUT" : "POST",
        v,
      );
      notify("主题已保存");
      onSaved();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function showPreview() {
    setBusy(true);
    setError("");
    try {
      setPreview(await api("/topics/preview", "POST", v));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={initial ? "编辑研究主题" : "订阅一个研究主题"}
      onClose={onClose}
      wide
    >
      <form onSubmit={save}>
        <p className="muted">描述你关注的方向，让论文自动来到你的阅读库。</p>
        <Field label="从主题模板开始">
          <select
            value={preset}
            onChange={(e) => {
              setPreset(e.target.value);
              const t = options.templates?.find(
                (x: Obj) => x.id === e.target.value,
              );
              if (t)
                setV((o) => ({
                  ...o,
                  name: t.name,
                  description: t.description,
                  keywords: t.keywords,
                  categories: t.categories,
                }));
            }}
          >
            <option value="">自定义主题</option>
            {options.templates?.map((t: Obj) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-grid">
          <Field label="主题名称">
            <input
              required
              maxLength={100}
              placeholder="例如：视觉语言导航"
              value={v.name}
              onChange={(e) => update("name", e.target.value)}
            />
          </Field>
          <Field label="检索频率">
            <select
              value={v.frequency}
              onChange={(e) => update("frequency", e.target.value)}
            >
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
              <option value="manual">仅手动</option>
            </select>
          </Field>
        </div>
        <Field label="研究描述">
          <textarea
            rows={2}
            placeholder="你希望持续关注哪些问题？"
            value={v.description}
            onChange={(e) => update("description", e.target.value)}
          />
        </Field>
        <Field
          label="检索关键词"
          hint="英文关键词效果更好；多个关键词用逗号分隔。模板会提供建议。"
        >
          <input
            required={!v.query}
            value={v.keywords.join(", ")}
            onChange={(e) => update("keywords", e.target.value.split(/[,，]/))}
            placeholder="vision-language navigation, VLN"
          />
        </Field>
        <Field label="每日最多阅读">
          <select
            value={customBudget ? "custom" : v.daily_limit}
            onChange={(e) => {
              setCustomBudget(e.target.value === "custom");
              if (e.target.value !== "custom")
                update("daily_limit", Number(e.target.value));
            }}
          >
            {[1, 3, 5, 10, 20].map((n) => (
              <option key={n} value={n}>
                {n} 篇 / 天
              </option>
            ))}
            <option value="custom">自定义</option>
          </select>
          {customBudget && (
            <input
              aria-label="自定义每日篇数"
              type="number"
              min={1}
              max={100}
              value={v.daily_limit}
              onChange={(e) => update("daily_limit", Number(e.target.value))}
            />
          )}
        </Field>
        <details className="advanced">
          <summary>
            <SlidersHorizontal size={16} />
            高级设置{" "}
            <small>
              {v.time} · {v.language === "zh" ? "中文" : "English"} ·{" "}
              {customDate ? "自定义日期" : `回溯 ${v.lookback_days} 天`}
            </small>
          </summary>
          <div className="form-grid">
            <Field label="论文来源">
              <select defaultValue="arxiv">
                <option value="arxiv">arXiv</option>
              </select>
            </Field>
            <Field label="总结语言">
              <select
                value={v.language}
                onChange={(e) => update("language", e.target.value)}
              >
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </Field>
            {v.frequency !== "manual" && (
              <>
                <Field label="执行时间">
                  <input
                    type="time"
                    required
                    value={v.time}
                    onChange={(e) => update("time", e.target.value)}
                  />
                </Field>
                <Field label="时区">
                  <input
                    list="timezones"
                    value={v.timezone}
                    onChange={(e) => update("timezone", e.target.value)}
                  />
                  <datalist id="timezones">
                    {options.timezones?.map((t: string) => (
                      <option key={t} value={t} />
                    ))}
                  </datalist>
                </Field>
              </>
            )}
            {v.frequency === "weekly" && (
              <Field label="每周执行日">
                <select
                  value={v.weekday}
                  onChange={(e) => update("weekday", Number(e.target.value))}
                >
                  {["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map(
                    (d, i) => (
                      <option key={i} value={i}>
                        {d}
                      </option>
                    ),
                  )}
                </select>
              </Field>
            )}
            <Field label="首次回溯范围">
              <select
                value={customDate ? "custom" : v.lookback_days}
                onChange={(e) => {
                  setCustomDate(e.target.value === "custom");
                  if (e.target.value !== "custom")
                    setV((o) => ({
                      ...o,
                      lookback_days: Number(e.target.value),
                      date_from: "",
                      date_to: "",
                    }));
                }}
              >
                {[7, 30, 90].map((n) => (
                  <option key={n} value={n}>
                    最近 {n} 天
                  </option>
                ))}
                {![7, 30, 90].includes(v.lookback_days) && (
                  <option value={v.lookback_days}>
                    最近 {v.lookback_days} 天
                  </option>
                )}
                <option value="custom">自定义日期</option>
              </select>
            </Field>
            <Field label="新版本策略">
              <select
                value={v.update_policy}
                onChange={(e) => update("update_policy", e.target.value)}
              >
                <option value="auto">自动阅读新版本</option>
                <option value="manual">仅记录更新，手动阅读</option>
              </select>
            </Field>
            {customDate && (
              <>
                <Field label="开始日期">
                  <input
                    required
                    type="date"
                    value={v.date_from}
                    onChange={(e) => update("date_from", e.target.value)}
                  />
                </Field>
                <Field label="结束日期">
                  <input
                    required
                    type="date"
                    value={v.date_to}
                    onChange={(e) => update("date_to", e.target.value)}
                  />
                </Field>
              </>
            )}
          </div>
          <div className="field">
            <span>学科类别</span>
            <MultiSelect
              value={v.categories}
              onChange={(a) => update("categories", a)}
              options={options.categories || {}}
              label="不限学科（可多选）"
            />
          </div>
          <Field label="排除关键词">
            <input
              value={v.exclusions.join(", ")}
              onChange={(e) =>
                update("exclusions", e.target.value.split(/[,，]/))
              }
              placeholder="用逗号分隔"
            />
          </Field>
          <Field label="重点关注问题">
            <textarea
              rows={2}
              value={v.questions}
              onChange={(e) => update("questions", e.target.value)}
              placeholder="例如：是否闭环？有哪些真实机器人实验？"
            />
          </Field>
          <Field label="高级检索表达式" hint="留空时系统根据关键词与类别生成。">
            <input
              value={v.query}
              onChange={(e) => update("query", e.target.value)}
              placeholder='例如：abs:"visual navigation" AND cat:cs.RO'
            />
          </Field>
        </details>
        {error && <div className="notice error">{error}</div>}
        {preview && (
          <div className="preview-results">
            <strong>检索预览 · 共 {preview.total} 条</strong>
            <small>{preview.note}</small>
            <code>{preview.query}</code>
            {preview.papers.map((p: Obj) => (
              <a key={p.identity} href={p.url} target="_blank" rel="noreferrer">
                {p.title}
                <ArrowUpRight size={14} />
              </a>
            ))}
          </div>
        )}
        <footer>
          <button
            type="button"
            className="btn secondary"
            disabled={busy}
            onClick={showPreview}
          >
            <Search size={16} />
            预览检索结果
          </button>
          <button className="btn primary" disabled={busy}>
            {busy ? "处理中…" : "保存主题"}
            <ChevronRight size={16} />
          </button>
        </footer>
      </form>
    </Modal>
  );
}
function ImportModal({
  topics,
  onClose,
  onSaved,
  notify,
}: {
  topics: Obj[];
  onClose: () => void;
  onSaved: (id?: string) => void;
  notify: (s: string) => void;
}) {
  const [tab, setTab] = useState("link");
  const [value, setValue] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [topic, setTopic] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      let r;
      if (tab === "link")
        r = await api("/imports/arxiv", "POST", {
          identifier: value,
          topic_id: topic || null,
        });
      else {
        const f = new FormData();
        f.append("file", file!);
        f.append("title", title);
        f.append("topic_id", topic);
        r = await api("/imports/pdf", "POST", f);
      }
      notify("导入已提交，阅读任务会在后台执行");
      onSaved(r.paper_id);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="导入论文" onClose={onClose}>
      <div className="tabs">
        <button
          className={tab === "link" ? "selected" : ""}
          onClick={() => setTab("link")}
        >
          arXiv 链接
        </button>
        <button
          className={tab === "pdf" ? "selected" : ""}
          onClick={() => setTab("pdf")}
        >
          本地 PDF
        </button>
      </div>
      <form onSubmit={submit}>
        {tab === "link" ? (
          <Field label="论文链接或 arXiv ID">
            <input
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="https://arxiv.org/abs/…"
            />
          </Field>
        ) : (
          <>
            <label className="upload-zone">
              <Upload size={28} />
              <strong>{file?.name || "选择一篇 PDF 论文"}</strong>
              <span>支持可检索文字的 PDF，最大 50 MB</span>
              <input
                required
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <Field label="论文标题（可选）">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="默认使用 PDF 标题或文件名"
              />
            </Field>
          </>
        )}
        <Field label="归入主题">
          <select value={topic} onChange={(e) => setTopic(e.target.value)}>
            <option value="">仅存入论文库</option>
            {topics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
        <p className="helper">
          原文保存在本地。启用阅读模型后，正文和所选图表页将发送至你配置的模型服务。
        </p>
        {error && <div className="notice error">{error}</div>}
        <footer>
          <button className="btn primary" disabled={busy}>
            {busy ? "正在导入…" : "导入并阅读"}
            <ArrowUpRight size={16} />
          </button>
        </footer>
      </form>
    </Modal>
  );
}
function SettingsPage({
  notify,
  onSaved,
}: {
  notify: (s: string) => void;
  onSaved: () => void;
}) {
  const [v, setV] = useState<Obj | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [usage, setUsage] = useState<Obj[]>([]);
  const [codexStatus, setCodexStatus] = useState<Obj | null>(null);
  const [customCodex, setCustomCodex] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/settings")
      .then(setV)
      .catch((e) => setError(e.message));
    api("/usage")
      .then(setUsage)
      .catch(() => {});
  }, []);
  const set = (k: string, val: any) => setV((o) => ({ ...o, [k]: val }));
  async function save(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      const s = await api("/settings", "PUT", v);
      setV({ ...s, api_key: "" });
      notify("设置已保存");
      onSaved();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function detectCodex() {
    if (!(await save())) return;
    setBusy(true);
    try {
      setCodexStatus(await api("/settings/codex/status", "POST", {}));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function probe() {
    if (!(await save())) return;
    try {
      await api("/settings/test", "POST", {});
      notify("已提交一次模型测试，请在任务中心查看结果");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function loadModels() {
    if (!(await save())) return;
    setBusy(true);
    try {
      setModels((await api("/settings/models", "POST", {})).models);
      notify("已获取服务端模型列表");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!v) return <div className="notice">{error || "正在加载设置…"}</div>;
  return (
    <div className="settings-grid">
      <form className="panel settings-form" onSubmit={save}>
        <div className="section-title">
          <span className="section-icon">
            <Globe size={21} />
          </span>
          <div>
            <h2>模型连接</h2>
            <p>连接一次，所有研究主题共享使用。</p>
          </div>
        </div>
        <div className="notice">
          本地保存论文与报告。启用后，阅读内容将发送到下方配置的模型服务。
        </div>
        <Field label="大模型接入方式">
          <select
            value={v.provider || "api"}
            onChange={(e) => set("provider", e.target.value)}
          >
            <option value="api">API 服务 · 使用 API Key</option>
            <option value="codex_cli">本机 Codex CLI · 使用已有登录</option>
          </select>
        </Field>
        {v.provider === "codex_cli" ? (
          <>
            <div className="notice">
              通过本机 codex exec 调用，复用 Codex CLI
              自己的登录。此模式无需在本工具填写 API Key。用量遵循当前 Codex
              登录账户的额度。
            </div>
            <button
              type="button"
              className="btn secondary"
              disabled={busy}
              onClick={detectCodex}
            >
              <RefreshCw size={16} />
              检测 CLI 与登录状态
            </button>
            {codexStatus && (
              <div
                className={
                  "notice " + (!codexStatus.authenticated ? "error" : "")
                }
              >
                {codexStatus.installed
                  ? `${codexStatus.version} · ${codexStatus.auth_method}`
                  : codexStatus.message}
                <p>{codexStatus.path}</p>
              </div>
            )}
            <Field label="Codex 模型">
              <select
                value={customCodex || v.codex_model ? "custom" : "default"}
                onChange={(e) => {
                  setCustomCodex(e.target.value === "custom");
                  if (e.target.value === "default") set("codex_model", "");
                }}
              >
                <option value="default">Codex 内置默认模型</option>
                <option value="custom">手动指定模型</option>
              </select>
              {(customCodex || v.codex_model) && (
                <input
                  aria-label="Codex 模型标识"
                  placeholder="填写当前账户可用的模型标识"
                  value={v.codex_model}
                  onChange={(e) => set("codex_model", e.target.value)}
                />
              )}
            </Field>
            <label className="check-row">
              <input
                type="checkbox"
                checked={v.codex_vision}
                onChange={(e) => set("codex_vision", e.target.checked)}
              />
              通过 Codex 解读图表页面（模型须支持图片）
            </label>
            <details className="advanced">
              <summary>CLI 路径与超时</summary>
              <Field label="Codex 可执行文件">
                <input
                  value={v.codex_path}
                  onChange={(e) => set("codex_path", e.target.value)}
                  placeholder="codex 或完整文件路径"
                />
              </Field>
              <Field label="单次调用超时">
                <select
                  value={v.codex_timeout_seconds}
                  onChange={(e) =>
                    set("codex_timeout_seconds", +e.target.value)
                  }
                >
                  {[60, 180, 300, 600, 1800].map((n) => (
                    <option key={n} value={n}>
                      {n} 秒
                    </option>
                  ))}
                </select>
              </Field>
            </details>
            <p className="helper">
              如尚未登录，请在终端运行 codex
              login。阅读任务以只读、临时会话运行，关闭无关工具与插件；不加载用户的自定义
              CLI 配置。请使用支持这些选项的新版 Codex CLI。
            </p>
          </>
        ) : (
          <>
            <Field label="API 接口类型">
              <select defaultValue="chat">
                <option value="chat">OpenAI 兼容 · Chat Completions</option>
              </select>
            </Field>
            <Field label="API 地址">
              <input
                required
                type="url"
                value={v.base_url}
                onChange={(e) => set("base_url", e.target.value)}
                placeholder="https://…/v1"
              />
            </Field>
            <Field
              label="API 密钥"
              hint={
                v.has_key
                  ? "已有密钥，留空保留。密钥不会返回到浏览器。"
                  : "本地模型服务如无需密钥，可留空。"
              }
            >
              <input
                type="password"
                autoComplete="new-password"
                value={v.api_key || ""}
                onChange={(e) => set("api_key", e.target.value)}
                placeholder={v.has_key ? "已保存 ········" : "输入 API 密钥"}
              />
            </Field>
            <button
              type="button"
              className="btn secondary"
              disabled={busy}
              onClick={loadModels}
            >
              <RefreshCw size={16} />
              保存连接并获取模型列表
            </button>
            <div className="form-grid">
              <Field label="正文阅读模型">
                <select
                  value={v.model}
                  onChange={(e) => set("model", e.target.value)}
                >
                  <option value="">请选择模型</option>
                  {Array.from(
                    new Set([v.model, ...models].filter(Boolean)),
                  ).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="图表视觉模型">
                <select
                  value={v.vision_model}
                  onChange={(e) => set("vision_model", e.target.value)}
                >
                  <option value="">暂不启用视觉解读</option>
                  {Array.from(
                    new Set([v.vision_model, ...models].filter(Boolean)),
                  ).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <p className="helper">
              模型列表不代表均支持视觉，请选择服务商明确支持图片输入的模型。
            </p>
          </>
        )}
        <label className="toggle-row">
          <div>
            <strong>启用自动模型阅读</strong>
            <small>未启用时，论文仍可导入、解析与浏览。</small>
          </div>
          <input
            type="checkbox"
            role="switch"
            checked={v.enabled}
            onChange={(e) => set("enabled", e.target.checked)}
          />
        </label>
        {v.provider !== "codex_cli" && (
          <details className="advanced">
            <summary>
              <SlidersHorizontal size={16} />
              高级兼容设置
            </summary>
            <Field label="手动填写正文模型标识">
              <input
                value={v.model}
                onChange={(e) => set("model", e.target.value)}
              />
            </Field>
            <Field label="手动填写视觉模型标识">
              <input
                value={v.vision_model}
                onChange={(e) => set("vision_model", e.target.value)}
              />
            </Field>
            <Field label="输出 token 参数">
              <select
                value={v.token_parameter}
                onChange={(e) => set("token_parameter", e.target.value)}
              >
                <option value="max_completion_tokens">
                  max_completion_tokens
                </option>
                <option value="max_tokens">max_tokens（部分兼容服务）</option>
              </select>
            </Field>
            <label className="check-row">
              <input
                type="checkbox"
                checked={v.json_mode}
                onChange={(e) => set("json_mode", e.target.checked)}
              />
              请求 JSON 格式（服务需支持）
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={v.clear_key || false}
                onChange={(e) => set("clear_key", e.target.checked)}
              />
              保存时清除已存密钥
            </label>
          </details>
        )}
        {error && <div className="notice error">{error}</div>}
        <footer>
          <button
            type="button"
            disabled={busy}
            className="btn secondary"
            onClick={probe}
          >
            <Play size={16} />
            测试一次调用
          </button>
          <button disabled={busy} className="btn primary">
            <Check size={16} />
            保存设置
          </button>
        </footer>
      </form>
      <div className="stack">
        <section className="panel">
          <h2>阅读额度</h2>
          <p className="muted">控制每天处理的论文量和模型用量。</p>
          <Field label="全局每日最多阅读">
            <select
              value={
                [5, 10, 20, 50, 100].includes(v.global_daily_limit)
                  ? v.global_daily_limit
                  : "custom"
              }
              onChange={(e) => {
                if (e.target.value !== "custom")
                  set("global_daily_limit", +e.target.value);
              }}
            >
              {[5, 10, 20, 50, 100].map((n) => (
                <option value={n} key={n}>
                  {n} 篇
                </option>
              ))}
              {![5, 10, 20, 50, 100].includes(v.global_daily_limit) && (
                <option value="custom">
                  当前值：{v.global_daily_limit} 篇
                </option>
              )}
            </select>
          </Field>
          <Field label="每日 token 额度">
            <select
              value={v.daily_token_limit}
              onChange={(e) => set("daily_token_limit", +e.target.value)}
            >
              {Array.from(
                new Set([
                  50000,
                  100000,
                  200000,
                  500000,
                  1000000,
                  v.daily_token_limit,
                ]),
              )
                .sort((a, b) => a - b)
                .map((n) => (
                  <option key={n} value={n}>
                    {n.toLocaleString()} tokens
                  </option>
                ))}
            </select>
          </Field>
          <div className="form-grid">
            <Field label="每次输出上限">
              <select
                value={v.max_output_tokens}
                onChange={(e) => set("max_output_tokens", +e.target.value)}
              >
                {[2000, 4000, 8000, 16000].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="图表页数量上限">
              <select
                value={v.max_vision_pages}
                onChange={(e) => set("max_vision_pages", +e.target.value)}
              >
                {[0, 2, 4, 6, 8, 12].map((n) => (
                  <option key={n} value={n}>
                    {n} 页
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <details className="advanced">
            <summary>解析与分块</summary>
            <Field label="单篇最多解析页数">
              <input
                type="number"
                min={1}
                max={500}
                value={v.max_pages}
                onChange={(e) => set("max_pages", +e.target.value)}
              />
            </Field>
            <Field label="每段正文字符数">
              <input
                type="number"
                min={4000}
                max={50000}
                value={v.chunk_chars}
                onChange={(e) => set("chunk_chars", +e.target.value)}
              />
            </Field>
          </details>
          <p className="helper">
            额度按北京时间每日重置。token
            按保守预留值控制，服务返回用量后结算；这不是精确费用预算。Codex CLI
            的单次实际 token
            不能硬性截断，本地额度仅在调用前拦截并在调用后记账。点击左侧“保存设置”统一保存。
          </p>
        </section>
        <section className="panel">
          <h2>模型调用记录</h2>
          {usage.length ? (
            usage.map((u, i) => (
              <div className="usage-row" key={i}>
                <strong>{u.model}</strong>
                <small>
                  {u.calls} 次 ·{" "}
                  {u.state === "succeeded" ? "响应成功" : "用量待确认"} · 输入{" "}
                  {u.input_tokens ?? "未知"} / 输出 {u.output_tokens ?? "未知"}
                </small>
              </div>
            ))
          ) : (
            <p className="muted">尚未调用模型服务。</p>
          )}
        </section>
      </div>
    </div>
  );
}
const confidenceLabel: Obj = { low: "低", medium: "中", high: "高" };
function QualityPanel({
  scores,
  pdf,
  reportId,
  notify,
}: {
  scores: Obj[];
  pdf: string;
  reportId: string;
  notify: (s: string) => void;
}) {
  const [selected, setSelected] = useState("");
  const available = scores.filter((a) => a.report_id === reportId);
  const a = available.find((x) => x.topic_id === selected) || available[0];
  return (
    <section className="panel quality-panel">
      <div className="section-head">
        <h2>质量评判与阅读优先级</h2>
        <button
          className="btn secondary small"
          onClick={async () => {
            try {
              const r = await api("/reports/" + reportId + "/assess", "POST");
              notify(
                r.jobs.length
                  ? "评分任务已提交；可在任务中心重试失败任务，完成后刷新论文"
                  : "先将论文归入研究主题，才能评价主题相关性",
              );
            } catch (e) {
              notify((e as Error).message);
            }
          }}
        >
          生成评分
        </button>
      </div>
      <p className="muted">
        模型辅助初评 · 创新性 25% / 指标效果 25% / 实验严谨完备 30% / 主题相关性
        20%。缺少证据时不强行给分。
      </p>
      {a ? (
        <>
          <label>
            评分主题{" "}
            <select
              aria-label="评分主题"
              value={a.topic_id}
              onChange={(e) => setSelected(e.target.value)}
            >
              {available.map((x) => (
                <option key={x.topic_id} value={x.topic_id}>
                  {x.topic_name}
                </option>
              ))}
            </select>
          </label>
          <div className="quality-totals">
            <strong>
              阅读优先分 {a.priority_score ?? "待确认"}
              {a.priority_score != null ? " / 100" : ""}
            </strong>
            <span>研究质量分 {a.quality_score ?? "待确认"}</span>
            <span>置信度：{confidenceLabel[a.confidence]}</span>
          </div>
          <p className="muted">
            研究质量分仅由前三项归一化计算。分数用于相同评分规则下的辅助排序，不是录用概率或绝对质量结论。
          </p>
          <div className="quality-totals">
            {a.dimensions.map((d: Obj) => (
              <span key={d.key}>
                {d.label} <strong>{d.score ?? "待确认"}</strong> / 5
              </span>
            ))}
          </div>
          <details>
            <summary>展开评分理由与原文依据</summary>
            <div className="quality-grid">
              {a.dimensions.map((d: Obj) => (
                <div className="quality-dimension" key={d.key}>
                  <h3>
                    {d.label}{" "}
                    <strong>
                      {d.score == null ? "证据不足" : d.score + " / 5"}
                    </strong>
                  </h3>
                  <p>{d.reason}</p>
                  <small>
                    权重 {d.weight}% · 置信度 {confidenceLabel[d.confidence]}
                  </small>
                  <details>
                    <summary>查看评分依据</summary>
                    {d.evidence.map((ref: Obj, i: number) => (
                      <div key={i}>
                        <a
                          href={asset(pdf) + "#page=" + ref.page}
                          target="_blank"
                          rel="noreferrer"
                        >
                          原文 p.{ref.page}
                        </a>
                        <blockquote>{ref.quote}</blockquote>
                      </div>
                    ))}
                  </details>
                </div>
              ))}
            </div>
            <h3>值得优先关注</h3>
            <ul>
              {a.strengths.map((x: string, i: number) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
            <h3>阅读时需要核对</h3>
            <ul>
              {a.weaknesses.map((x: string, i: number) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </details>
          <p className="muted">
            {a.caveat} · 评分规则 v{a.rubric_version} · {stamp(a.created)}
          </p>
        </>
      ) : (
        <p>
          待评分：尚无当前报告与主题配置下的有效评分。只有完成全文阅读、证据充分的论文才进入推荐排序；旧报告的评分不会套用到新版。
        </p>
      )}
    </section>
  );
}

function PaperDetail({
  id,
  onBack,
  notify,
  onChanged,
}: {
  id: string;
  onBack: () => void;
  notify: (s: string) => void;
  onChanged: () => void;
}) {
  const [p, setP] = useState<Obj | null>(null);
  const [vi, setVi] = useState("");
  const [ri, setRi] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState("report");
  const [includePdf, setIncludePdf] = useState(false);
  const load = () =>
    api("/papers/" + id)
      .then((r) => {
        setP(r);
        setNotes(r.notes);
        setVi((v) => v || r.versions[0]?.id);
      })
      .catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, [id]);
  if (!p) return <div className="notice">{error || "正在加载论文…"}</div>;
  const v = p.versions.find((x: Obj) => x.id === vi) || p.versions[0];
  const reports = v?.reports || [];
  const r = reports.find((x: Obj) => x.id === ri) || reports[0];
  const report = r?.content;
  const ext = v?.extraction;
  async function state(update: Obj) {
    try {
      await api("/papers/" + id, "PATCH", update);
      setP((o) => ({ ...o, ...update }));
      onChanged();
      return true;
    } catch (e) {
      notify((e as Error).message);
      return false;
    }
  }
  async function read(force = false) {
    try {
      await api("/versions/" + v.id + "/read", "POST", {
        language: report?.language || "zh",
        force,
      });
      notify("阅读任务已加入队列，可在任务中心查看进度");
    } catch (e) {
      notify((e as Error).message);
    }
  }
  return (
    <div className="detail">
      <button className="back" onClick={onBack}>
        <ArrowLeft size={16} />
        返回论文库
      </button>
      <div className="detail-heading">
        <div className="paper-meta">
          <span>{p.source === "arxiv" ? "arXiv" : "本地导入"}</span>
          <span>{p.published?.slice(0, 10) || stamp(p.created)}</span>
          <Pill value={v.status} />
        </div>
        <h1>{p.title}</h1>
        <p className="authors">{p.authors.join(" · ") || "作者信息未提供"}</p>
        <div className="detail-actions">
          <button
            className={"btn " + (p.favorite ? "accent" : "secondary")}
            onClick={() => state({ favorite: !p.favorite })}
          >
            <Star size={16} fill={p.favorite ? "currentColor" : "none"} />
            {p.favorite ? "已收藏" : "收藏"}
          </button>
          <button
            className="btn secondary"
            onClick={() => state({ is_read: !p.is_read })}
          >
            <Check size={16} />
            {p.is_read ? "标为未读" : "标为已读"}
          </button>
          {v.pdf_path && (
            <a
              className="btn secondary"
              href={asset(v.pdf_path)}
              target="_blank"
              rel="noreferrer"
            >
              <FileText size={16} />
              原文 PDF
              <ArrowUpRight size={14} />
            </a>
          )}
          {p.url && (
            <a
              className="btn secondary"
              href={p.url}
              target="_blank"
              rel="noreferrer"
            >
              论文主页
              <ArrowUpRight size={14} />
            </a>
          )}
          <button className="btn primary" onClick={() => read(!!report)}>
            <Play size={16} />
            {report ? "重新阅读" : "生成总结"}
          </button>
          <button className="icon-btn" aria-label="刷新论文" onClick={load}>
            <RefreshCw size={17} />
          </button>
        </div>
      </div>
      <div className="version-bar">
        <span>
          <Layers size={16} />
          论文版本
        </span>
        <select
          aria-label="论文版本"
          value={vi}
          onChange={(e) => {
            setVi(e.target.value);
            setRi("");
          }}
        >
          {p.versions.map((v: Obj) => (
            <option key={v.id} value={v.id}>
              {v.label} · {stamp(v.created)}
            </option>
          ))}
        </select>
        {reports.length > 0 && (
          <select
            aria-label="报告修订"
            value={r?.id || ""}
            onChange={(e) => setRi(e.target.value)}
          >
            {reports.map((r: Obj, i: number) => (
              <option key={r.id} value={r.id}>
                总结修订 {reports.length - i} · {stamp(r.created)}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="tabs">
        <button
          className={tab === "report" ? "selected" : ""}
          onClick={() => setTab("report")}
        >
          阅读报告
        </button>
        <button
          className={tab === "source" ? "selected" : ""}
          onClick={() => setTab("source")}
        >
          原文与页面
        </button>
        <button
          className={tab === "notes" ? "selected" : ""}
          onClick={() => setTab("notes")}
        >
          个人笔记
        </button>
      </div>
      {tab === "notes" ? (
        <section className="panel">
          <h2>我的阅读笔记</h2>
          <p className="muted">笔记独立保存，不会被论文更新或重新阅读覆盖。</p>
          <textarea
            aria-label="个人笔记"
            rows={12}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="记录你的思考、疑问和实验想法…"
          />
          <button
            className="btn primary"
            onClick={async () => {
              if (await state({ notes })) notify("笔记已保存");
            }}
          >
            保存笔记
          </button>
        </section>
      ) : tab === "source" ? (
        <div className="stack">
          <section className="panel">
            <h2>摘要</h2>
            <p className="abstract">
              {p.abstract || "本地导入文件没有独立摘要元数据。请查看原文页面。"}
            </p>
          </section>
          {ext && (
            <>
              <div className="notice">
                已解析 {ext.processed_pages} / {ext.total_pages} 页。
                {ext.reading_order}
                {ext.warnings.map((w: string) => (
                  <p key={w}>{w}</p>
                ))}
              </div>
              <div className="page-grid">
                {ext.pages.map((page: Obj) => (
                  <a
                    key={page.page}
                    href={asset(v.pdf_path) + "#page=" + page.page}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <img
                      loading="lazy"
                      src={asset(page.image)}
                      alt={"原文第 " + page.page + " 页"}
                    />
                    <span>
                      第 {page.page} 页 · {page.chars} 字符
                      <ArrowUpRight size={14} />
                    </span>
                  </a>
                ))}
              </div>
            </>
          )}
        </div>
      ) : report ? (
        <div className="report-layout">
          <article>
            <QualityPanel
              scores={p.assessments || []}
              pdf={v.pdf_path}
              reportId={r.id}
              notify={notify}
            />
            <section className="report-overview">
              <span className="eyebrow">READING BRIEF</span>
              <h2>论文速览</h2>
              {report.summary_sections?.length ? (
                report.summary_sections.map((section: Obj, i: number) => (
                  <div className="brief-section" key={i}>
                    <h3>{section.section}</h3>
                    <p style={{ whiteSpace: "pre-line" }}>{section.text}</p>
                    <details>
                      <summary>查看原文依据</summary>
                      {section.evidence.map((ref: Obj, j: number) => (
                        <div key={j}>
                          <a
                            href={asset(v.pdf_path) + "#page=" + ref.page}
                            target="_blank"
                            rel="noreferrer"
                          >
                            原文 p.{ref.page}
                          </a>
                          <blockquote>{ref.quote}</blockquote>
                        </div>
                      ))}
                    </details>
                  </div>
                ))
              ) : (
                <p>{report.summary}</p>
              )}
              <div className="report-foot">
                {report.processed_pages}/{report.total_pages} 页 ·{" "}
                {report.visual_mode === "vision"
                  ? "包含视觉解读"
                  : "原图与图注模式"}{" "}
                · {stamp(report.created)}
              </div>
            </section>
            {report.warnings.length > 0 && (
              <details className="notice">
                <summary>
                  {report.warnings.length} 项阅读限制与待核对内容
                </summary>
                {report.warnings.map((w: string, i: number) => (
                  <p key={i}>{w}</p>
                ))}
              </details>
            )}
            {Array.from(
              new Set<string>(report.items.map((i: Obj) => i.section)),
            ).map((section: string, si: number) => (
              <section
                className="report-section"
                key={section}
                id={"section-" + si}
              >
                <div className="section-number">
                  {String(si + 1).padStart(2, "0")}
                </div>
                <div>
                  <h2>{section}</h2>
                  {report.items
                    .filter((i: Obj) => i.section === section)
                    .map((item: Obj, i: number) => (
                      <div className="claim" key={i}>
                        <span className={"claim-label " + item.kind}>
                          {
                            (
                              {
                                author_claim: "作者报告",
                                analysis: "系统分析",
                                uncertain: "待确认",
                              } as Obj
                            )[item.kind]
                          }
                        </span>
                        <p>{item.text}</p>
                        {!item.verified && (
                          <span className="warn-text">原文引用待核对</span>
                        )}
                        <div className="evidence-links">
                          {item.evidence.map((e: Obj, j: number) => (
                            <a
                              title={e.quote}
                              href={asset(v.pdf_path) + "#page=" + e.page}
                              key={j}
                              target="_blank"
                              rel="noreferrer"
                            >
                              原文 p.{e.page}
                              <ArrowUpRight size={11} />
                            </a>
                          ))}
                        </div>
                        {item.evidence.length > 0 && (
                          <details className="source-quotes">
                            <summary>查看原文依据</summary>
                            {item.evidence.map((e: Obj, j: number) => (
                              <blockquote key={j}>
                                {e.quote}
                                <small>
                                  PDF p.{e.page} · {e.block_id}
                                </small>
                              </blockquote>
                            ))}
                          </details>
                        )}
                      </div>
                    ))}
                </div>
              </section>
            ))}
            {report.figures.length > 0 && (
              <section id="figures" className="panel">
                <h2>关键图表解读</h2>
                {report.figures.map((f: Obj, i: number) => (
                  <figure key={i}>
                    <a
                      href={asset(v.pdf_path) + "#page=" + f.page}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <img
                        src={asset(f.image)}
                        alt={"论文第 " + f.page + " 页图表预览"}
                      />
                    </a>
                    <figcaption>
                      <strong>{f.label}</strong>
                      <span className="pill">原文整页预览 · p.{f.page}</span>
                      <p>{f.description}</p>
                      <details>
                        <summary>原文图注</summary>
                        <p>{f.caption}</p>
                      </details>
                    </figcaption>
                  </figure>
                ))}
              </section>
            )}
          </article>
          <aside className="report-side">
            <section className="panel">
              <h3>阅读导航</h3>
              {Array.from(
                new Set<string>(report.items.map((i: Obj) => i.section)),
              ).map((s, i) => (
                <a key={s} href={"#section-" + i}>
                  {s}
                  <ChevronRight size={13} />
                </a>
              ))}
              {report.figures.length > 0 && (
                <a href="#figures">
                  图表解读
                  <ChevronRight size={13} />
                </a>
              )}
            </section>
            <section className="panel">
              <h3>保存到本地</h3>
              <p className="helper">Markdown 总结与原图打包，支持离线阅读。</p>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={includePdf}
                  onChange={(e) => setIncludePdf(e.target.checked)}
                />
                附带原文 PDF
              </label>
              <a
                className="btn secondary full"
                href={
                  "/api/reports/" + r.id + "/export?include_pdf=" + includePdf
                }
              >
                <Download size={16} />
                导出图文档案
              </a>
            </section>
            <p className="helper">{report.quality_note}</p>
            <details className="helper">
              <summary>生成信息</summary>
              <p>
                {report.model} · 提示词 v{report.prompt_version}
              </p>
            </details>
          </aside>
        </div>
      ) : (
        <section className="panel">
          <Empty
            title={ext ? "全文已经准备好" : "论文已加入阅读库"}
            icon={FileText}
            action={
              <button className="btn primary" onClick={() => read()}>
                <Play size={16} />
                生成阅读报告
              </button>
            }
          >
            {ext
              ? "配置并启用模型后，即可生成带原文引用的图文总结。可先在“原文与页面”中浏览论文。"
              : "后台任务将下载并解析原文。可在任务中心查看进度，或稍后刷新此页。"}
          </Empty>
        </section>
      )}
    </div>
  );
}
function App() {
  const [view, setView] = useState("home");
  const [topics, setTopics] = useState<Obj[]>([]);
  const [stats, setStats] = useState<Obj>({});
  const [options, setOptions] = useState<Obj>({});
  const [papers, setPapers] = useState<Obj[]>([]);
  const [total, setTotal] = useState(0);
  const [jobs, setJobs] = useState<Obj[]>([]);
  const [scans, setScans] = useState<Obj[]>([]);
  const [filter, setFilter] = useState("");
  const [q, setQ] = useState("");
  const [fav, setFav] = useState(false);
  const [unread, setUnread] = useState(false);
  const [scope, setScope] = useState("");
  const [sort, setSort] = useState("recent");
  const [source, setSource] = useState("");
  const [excluded, setExcluded] = useState(false);
  const [offset, setOffset] = useState(0);
  const [paperId, setPaperId] = useState("");
  const [modal, setModal] = useState<"topic" | "import" | "cleanup" | null>(
    null,
  );
  const [edit, setEdit] = useState<Obj | undefined>();
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const notify = (s: string) => {
    setToast(s);
    setTimeout(() => setToast(""), 5000);
  };
  const refresh = () => setVersion((n) => n + 1);
  const nav = (v: string, topic = "") => {
    setView(v);
    setSort(v === "recommend" ? "priority" : "recent");
    setQ("");
    setScope("");
    setSource("");
    setFav(false);
    setUnread(v === "recommend");
    setPaperId("");
    setFilter(topic);
    setExcluded(false);
    setOffset(0);
    setError("");
  };
  useEffect(() => {
    api("/options")
      .then(setOptions)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    const load = () =>
      Promise.all([api("/topics"), api("/stats"), api("/jobs"), api("/scans")])
        .then(([t, s, j, sc]) => {
          setTopics(t);
          setStats(s);
          setJobs(j);
          setScans(sc);
        })
        .catch((e) => setError(e.message));
    load();
    const timer = setInterval(load, 7000);
    return () => clearInterval(timer);
  }, [version]);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      const qs = new URLSearchParams({
        q,
        topic: filter,
        sort,
        ranked_only: String(view === "recommend"),
        favorite: String(fav),
        unread: String(unread),
        scope,
        source,
        excluded: String(excluded),
        offset: String(offset),
      });
      api("/papers?" + qs)
        .then((r) => {
          if (!cancelled) {
            setPapers(r.items);
            setTotal(r.total);
            setError("");
          }
        })
        .catch((e) => !cancelled && setError(e.message))
        .finally(() => !cancelled && setLoading(false));
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [
    q,
    filter,
    fav,
    unread,
    scope,
    source,
    excluded,
    offset,
    version,
    sort,
    view,
    stats.pending,
    stats.reports,
    stats.papers,
  ]);
  const action = async (path: string, method = "POST", body?: Obj) => {
    try {
      await api(path, method, body);
      refresh();
    } catch (e) {
      notify((e as Error).message);
    }
  };
  const current = topics.find((t) => t.id === filter);
  const heading = paperId
    ? "论文详情"
    : view === "home"
      ? "研究概览"
      : view === "recommend"
        ? "推荐阅读"
        : view === "library"
          ? current?.name || "论文库"
          : view === "topics"
            ? "研究主题"
            : view === "jobs"
              ? "任务中心"
              : "设置";
  return (
    <div className="shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            nav("home");
          }}
        >
          <span className="brand-mark">
            <BookOpen size={22} />
          </span>
          <div>
            AutoReadPaper<small>你的研究，持续生长</small>
          </div>
        </a>
        <span className="nav-label">工作空间</span>
        <nav>
          {[
            { id: "home", label: "研究概览", icon: Radio },
            { id: "library", label: "论文库", icon: Library },
            { id: "recommend", label: "推荐阅读", icon: Star },
            { id: "topics", label: "研究主题", icon: Layers },
            { id: "jobs", label: "任务中心", icon: Activity },
          ].map((n) => (
            <button
              key={n.id}
              className={view === n.id ? "active" : ""}
              onClick={() => nav(n.id)}
            >
              <n.icon size={19} />
              {n.label}
              {n.id === "library" && <span>{stats.papers || 0}</span>}
              {n.id === "jobs" && !!stats.pending && <i className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="nav-label topic-label">
          我的主题
          <button
            className="icon-btn"
            aria-label="添加主题"
            onClick={() => {
              setEdit(undefined);
              setModal("topic");
            }}
          >
            <Plus size={15} />
          </button>
        </div>
        <div className="topic-nav">
          {topics.length ? (
            topics.map((t, i) => (
              <button
                key={t.id}
                className={filter === t.id ? "chosen" : ""}
                onClick={() => nav("library", t.id)}
              >
                <i className={"topic-dot color-" + (i % 4)} />
                <span>{t.name}</span>
                <small>{t.paper_count}</small>
              </button>
            ))
          ) : (
            <p>还没有订阅主题</p>
          )}
        </div>
        <div className="sidebar-bottom">
          <button
            className={view === "settings" ? "active" : ""}
            onClick={() => nav("settings")}
          >
            <Settings size={18} />
            设置
          </button>
          <div className="local-status">
            <span className="status-dot" />
            <div>
              本地工作空间<small>数据保存在这台电脑</small>
            </div>
            <span className="version">v0.1</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            工作空间
            <ChevronRight size={13} />
            <strong>{heading}</strong>
          </div>
          <span className="local-badge">
            <span className="status-dot" />
            LOCAL
          </span>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {view === "home"
                  ? "YOUR RESEARCH, IN FOCUS"
                  : "RESEARCH WORKSPACE"}
              </span>
              <h1>{heading}</h1>
              <p>
                {view === "home"
                  ? "从发现到理解，为每一次研究积累。"
                  : view === "recommend"
                    ? "结合论文证据和研究主题，决定下一篇先读什么。"
                    : view === "library"
                      ? "集中浏览论文、阅读报告和你的思考。"
                      : view === "topics"
                        ? "告诉我们你关心什么，其余交给持续阅读。"
                        : view === "jobs"
                          ? "每一次检索和阅读，都有迹可循。"
                          : view === "settings"
                            ? "配置你的阅读环境，按自己的节奏运行。"
                            : ""}
              </p>
            </div>
            {!paperId && view !== "settings" && (
              <div className="heading-actions">
                <button
                  className="btn secondary"
                  onClick={() => setModal("import")}
                >
                  <Upload size={16} />
                  导入论文
                </button>
                <button
                  className="btn primary"
                  onClick={() => {
                    setEdit(undefined);
                    setModal("topic");
                  }}
                >
                  <Plus size={17} />
                  新建主题
                </button>
              </div>
            )}
          </div>
          {error && (
            <div role="alert" className="notice error">
              {error}
              <button onClick={refresh}>重试</button>
            </div>
          )}
          {paperId ? (
            <PaperDetail
              key={paperId}
              id={paperId}
              onBack={() => setPaperId("")}
              notify={notify}
              onChanged={refresh}
            />
          ) : view === "settings" ? (
            <SettingsPage notify={notify} onSaved={refresh} />
          ) : view === "topics" ? (
            <>
              <div className="topic-grid">
                {topics.map((t, i) => (
                  <section className="panel topic-card" key={t.id}>
                    <div className="topic-card-top">
                      <span className={"topic-icon color-" + (i % 4)}>
                        <Layers size={23} />
                      </span>
                      <Pill value={t.active ? "订阅中" : "已暂停"} />
                    </div>
                    <h2>{t.name}</h2>
                    <p>{t.description || "自定义研究主题"}</p>
                    <div className="tags">
                      {t.keywords.slice(0, 4).map((k: string) => (
                        <span key={k}>{k}</span>
                      ))}
                    </div>
                    <div className="topic-numbers">
                      <span>
                        <strong>{t.paper_count}</strong> 篇论文
                      </span>
                      <span>{t.daily_limit} 篇 / 天</span>
                    </div>
                    <small className="muted">
                      下次检索：{t.active ? stamp(t.next_run) : "已暂停"}
                    </small>
                    <footer>
                      <button
                        className="text-btn"
                        onClick={() => nav("library", t.id)}
                      >
                        浏览论文
                        <ChevronRight size={15} />
                      </button>
                      <div>
                        <TopicAction
                          className="icon-btn"
                          hint="立即检索一次：查找新论文，并按阅读预算处理；不改变定时设置。"
                          aria-label={"检索" + t.name}
                          onClick={() => {
                            action("/topics/" + t.id + "/scan");
                            notify("检索任务已提交");
                          }}
                        >
                          <Search size={16} />
                        </TopicAction>
                        <TopicAction
                          className="icon-btn"
                          aria-label={"编辑" + t.name}
                          hint="编辑主题：修改关键词、关注问题、检索频率和阅读预算。"
                          onClick={() => {
                            setEdit(t);
                            setModal("topic");
                          }}
                        >
                          <SlidersHorizontal size={16} />
                        </TopicAction>
                        <TopicAction
                          className="icon-btn"
                          hint={
                            t.active
                              ? "暂停订阅的自动处理，保留已有论文、报告与评分。"
                              : t.frequency === "manual"
                                ? "恢复订阅：当前为手动检索，不会自动开启定时检索。"
                                : "恢复订阅：按已设置的频率检索并处理新论文。"
                          }
                          aria-label={"切换订阅" + t.name}
                          onClick={() =>
                            action("/topics/" + t.id, "PATCH", {
                              active: !t.active,
                            })
                          }
                        >
                          {t.active ? <Pause size={16} /> : <Power size={16} />}
                        </TopicAction>
                        <TopicAction
                          className="icon-btn"
                          hint="删除主题：取消该主题的待处理任务，保留已有论文、报告和笔记。"
                          aria-label={"删除主题" + t.name}
                          onClick={() => {
                            if (
                              window.confirm(
                                `删除主题“${t.name}”？该主题的待处理任务将取消，已有论文、阅读报告及笔记会保留。`,
                              )
                            ) {
                              action("/topics/" + t.id, "DELETE");
                            }
                          }}
                        >
                          <Trash2 size={16} />
                        </TopicAction>
                      </div>
                    </footer>
                  </section>
                ))}
              </div>
              {!topics.length && (
                <section className="panel">
                  <Empty
                    title="从一个研究问题开始"
                    icon={Layers}
                    action={
                      <button
                        className="btn primary"
                        onClick={() => {
                          setEdit(undefined);
                          setModal("topic");
                        }}
                      >
                        <Plus size={16} />
                        创建第一个主题
                      </button>
                    }
                  >
                    选择主题模板，或描述自己的研究方向。设定频率后，系统会定期寻找新论文。
                  </Empty>
                </section>
              )}
            </>
          ) : view === "jobs" ? (
            <div className="stack">
              <section className="panel">
                <div className="section-head">
                  <h2>
                    任务队列 <span className="count">{jobs.length}</span>
                  </h2>
                  <button className="btn secondary small" onClick={refresh}>
                    <RefreshCw size={14} />
                    刷新
                  </button>
                </div>
                {jobs.length ? (
                  <div className="job-list">
                    {jobs.map((j) => (
                      <div className="job-row" key={j.id}>
                        <div className={"job-icon " + j.state}>
                          {j.state === "succeeded" ? (
                            <CheckCircle2 size={19} />
                          ) : j.state === "failed" ? (
                            <AlertCircle size={19} />
                          ) : (
                            <Clock size={19} />
                          )}
                        </div>
                        <div className="job-body">
                          <strong>
                            {
                              {
                                scan: "检索主题论文",
                                read: "阅读全文并生成报告",
                                assess: "质量评判与优先级评分",
                                summary: "生成详细速览",
                                import: "导入 arXiv 论文",
                                probe: "测试模型连接",
                              }[j.kind as string]
                            }
                            {j.payload.config?.name &&
                              " · " + j.payload.config.name}
                          </strong>
                          <p>{j.error || j.progress || "等待 Worker 处理"}</p>
                          <small>
                            {stamp(j.created)} · 尝试 {j.attempts} 次
                          </small>
                        </div>
                        <Pill value={j.state} />
                        <div className="job-actions">
                          {[
                            "blocked",
                            "failed",
                            "cancelled",
                            "retry_wait",
                          ].includes(j.state) && (
                            <button
                              className="icon-btn"
                              aria-label={"重试任务" + j.id}
                              title="重试"
                              onClick={() => action("/jobs/" + j.id + "/retry")}
                            >
                              <RefreshCw size={16} />
                            </button>
                          )}
                          {!["succeeded", "cancelled"].includes(j.state) && (
                            <button
                              className="icon-btn"
                              aria-label={"取消任务" + j.id}
                              title="取消"
                              onClick={() =>
                                action("/jobs/" + j.id + "/cancel")
                              }
                            >
                              <X size={16} />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Empty title="任务队列是空的" icon={Activity}>
                    创建主题后手动检索，或导入一篇论文，即可开始。
                  </Empty>
                )}
              </section>
              {scans.length > 0 && (
                <section className="panel">
                  <h2>检索记录</h2>
                  {scans.map((s) => (
                    <div className="scan-row" key={s.id}>
                      <div>
                        <strong>
                          {topics.find((t) => t.id === s.topic_id)?.name ||
                            "已删除主题"}
                        </strong>
                        <small>
                          {stamp(s.created)} · 已扫描 {s.offset} 条 · 新增版本{" "}
                          {s.found} 条
                        </small>
                      </div>
                      <Pill value={s.complete ? "扫描完整" : "扫描未完成"} />
                    </div>
                  ))}
                </section>
              )}
            </div>
          ) : (
            <>
              {view === "home" && (
                <>
                  <section className="welcome">
                    <div>
                      <span className="eyebrow">
                        A LITTLE CURIOSITY, EVERY DAY
                      </span>
                      <h2>
                        让新论文，
                        <br />
                        成为你的研究积累。
                      </h2>
                      <p>
                        订阅感兴趣的方向，自动发现、阅读并整理。
                        <br />
                        留出更多时间，思考真正重要的问题。
                      </p>
                      <button
                        className="btn dark"
                        onClick={() => {
                          setEdit(undefined);
                          setModal("topic");
                        }}
                      >
                        {topics.length
                          ? "探索新的研究主题"
                          : "开启你的研究订阅"}
                        <ArrowUpRight size={16} />
                      </button>
                    </div>
                    <div className="paper-illustration" aria-hidden="true">
                      <div className="orbit orbit-one" />
                      <div className="orbit orbit-two" />
                      <div className="float-chip chip-top">
                        <Search size={15} />
                        发现
                      </div>
                      <div className="illustrated-paper back-paper" />
                      <div className="illustrated-paper">
                        <div className="paper-label">
                          RESEARCH NOTE <BookOpen size={15} />
                        </div>
                        <div className="ink-line long" />
                        <div className="ink-line mid" />
                        <div className="chart">
                          <i />
                          <i />
                          <i />
                          <i />
                          <i />
                          <svg viewBox="0 0 170 60">
                            <path d="M0 54 L30 42 L55 47 L90 22 L120 27 L170 3" />
                          </svg>
                        </div>
                        <div className="ink-line" />
                        <div className="ink-line" />
                        <div className="ink-line mid" />
                        <div className="paper-bottom">
                          <span />
                          <span>READ · UNDERSTAND · KEEP</span>
                        </div>
                      </div>
                      <div className="float-chip chip-bottom">
                        <CheckCircle2 size={16} />
                        理解，留存。
                      </div>
                    </div>
                  </section>
                  <div className="stats-grid">
                    {[
                      {
                        label: "订阅主题",
                        value: stats.topics || 0,
                        icon: Layers,
                        note: "持续关注的研究方向",
                      },
                      {
                        label: "论文收藏库",
                        value: stats.papers || 0,
                        icon: Library,
                        note: "发现与导入的论文",
                      },
                      {
                        label: "阅读报告",
                        value: stats.reports || 0,
                        icon: BookOpen,
                        note: "可回溯原文的总结",
                      },
                      {
                        label: "待处理任务",
                        value: stats.pending || 0,
                        icon: Activity,
                        note: "排队、运行或等待条件",
                      },
                    ].map((s) => (
                      <div className="stat-card" key={s.label}>
                        <div>
                          <span>{s.label}</span>
                          <s.icon size={18} />
                        </div>
                        <strong>
                          {s.value}
                          <small>
                            {s.label === "订阅主题"
                              ? "个"
                              : s.label === "待处理任务"
                                ? "项"
                                : "篇"}
                          </small>
                        </strong>
                        <p>{s.note}</p>
                      </div>
                    ))}
                  </div>
                  {!stats.model_ready && (
                    <div className="setup-notice">
                      <span className="notice-symbol">
                        <SlidersHorizontal size={20} />
                      </span>
                      <div>
                        <strong>接入阅读模型，开启图文总结</strong>
                        <p>
                          你可以先导入论文。原文解析完成后，任务会等待模型配置。
                        </p>
                      </div>
                      <button
                        className="text-btn"
                        onClick={() => nav("settings")}
                      >
                        前往设置
                        <ArrowUpRight size={16} />
                      </button>
                    </div>
                  )}
                </>
              )}
              {view === "recommend" && (
                <div className="notice recommendation-notice">
                  <strong>按阅读优先分推荐 · 默认只看未读</strong>
                  <p>
                    创新性 25% + 效果 25% + 实验严谨完备 30% + 相关性
                    20%。仅显示当前已评分的全文报告；未读全文、证据不足或主题变更后待更新的论文不参与排名。全部主题下取每篇论文的最高匹配主题分；同分按最近入库排序。评分是基于论文证据的模型初评，未外部查新或独立复现。
                  </p>
                  <button
                    className="btn secondary small"
                    onClick={async () => {
                      await action("/assessments/backfill");
                      notify(
                        "已为已处理且归入主题的论文补充评分任务，请在任务中心查看",
                      );
                    }}
                  >
                    为已处理论文补充评分
                  </button>
                </div>
              )}
              <section className="library-section">
                {view === "library" && (
                  <div className="cleanup-entry">
                    <button
                      className="btn secondary small"
                      onClick={() => setModal("cleanup")}
                    >
                      <Trash2 size={14} />
                      清理论文库
                    </button>
                  </div>
                )}
                <div className="section-head">
                  <div>
                    <h2>
                      {view === "home"
                        ? "最近入库"
                        : view === "recommend"
                          ? "优先阅读清单"
                          : "全部论文"}{" "}
                      <span className="count">{total}</span>
                    </h2>
                    {current && <p className="muted">{current.description}</p>}
                  </div>
                  {view === "home" ? (
                    <button className="text-btn" onClick={() => nav("library")}>
                      查看全部
                      <ChevronRight size={16} />
                    </button>
                  ) : (
                    <button className="btn secondary small" onClick={refresh}>
                      <RefreshCw size={14} />
                      刷新
                    </button>
                  )}
                </div>
                <div className="toolbar">
                  <select
                    aria-label="论文排序"
                    value={sort}
                    onChange={(e) => {
                      setSort(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="priority">阅读优先分从高到低</option>
                    <option value="recent">最近入库</option>
                  </select>
                  <div className="search-box">
                    <Search size={18} />
                    <input
                      aria-label="搜索论文"
                      placeholder="搜索标题、作者、总结或笔记…"
                      value={q}
                      onChange={(e) => {
                        setQ(e.target.value);
                        setOffset(0);
                      }}
                    />
                    {q && (
                      <button
                        className="icon-btn"
                        aria-label="清除搜索"
                        onClick={() => setQ("")}
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                  <select
                    aria-label="筛选主题"
                    value={filter}
                    onChange={(e) => {
                      setFilter(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">全部主题</option>
                    {topics.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                  <button
                    className={"filter-button " + (fav ? "selected" : "")}
                    onClick={() => {
                      setFav(!fav);
                      setOffset(0);
                    }}
                  >
                    <Star size={15} />
                    收藏
                  </button>
                  <button
                    className={"filter-button " + (unread ? "selected" : "")}
                    onClick={() => {
                      setUnread(!unread);
                      setOffset(0);
                    }}
                  >
                    未读
                  </button>
                  <details className="filter-more">
                    <summary>
                      <SlidersHorizontal size={16} />
                    </summary>
                    <div>
                      <Field label="阅读范围">
                        <select
                          value={scope}
                          onChange={(e) => {
                            setScope(e.target.value);
                            setOffset(0);
                          }}
                        >
                          <option value="">全部状态</option>
                          {[
                            "metadata_only",
                            "extracted",
                            "partial_fulltext",
                            "fulltext",
                          ].map((s) => (
                            <option key={s} value={s}>
                              {labels[s]}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field label="来源">
                        <select
                          value={source}
                          onChange={(e) => {
                            setSource(e.target.value);
                            setOffset(0);
                          }}
                        >
                          <option value="">全部来源</option>
                          <option value="arxiv">arXiv</option>
                          <option value="local">本地 PDF</option>
                        </select>
                      </Field>
                      {filter && (
                        <label className="check-row">
                          <input
                            type="checkbox"
                            checked={excluded}
                            onChange={(e) => setExcluded(e.target.checked)}
                          />
                          查看此主题排除项
                        </label>
                      )}
                    </div>
                  </details>
                </div>
                {loading ? (
                  <div className="loading">
                    <span />
                    正在整理阅读库…
                  </div>
                ) : papers.length ? (
                  <div className="paper-list">
                    {papers.map((p, index) => (
                      <article className="paper-card" key={p.id}>
                        <div
                          className="paper-thumbnail"
                          onClick={() => setPaperId(p.id)}
                        >
                          <FileText size={29} />
                          <small>
                            {p.source === "arxiv" ? "arXiv" : "PDF"}
                          </small>
                        </div>
                        <div className="paper-info">
                          <div className="paper-meta">
                            <span>
                              {p.source === "arxiv" ? "arXiv" : "本地 PDF"}
                            </span>
                            <span>
                              {p.published?.slice(0, 10) || stamp(p.created)}
                            </span>
                            <Pill
                              value={p.versions[0]?.status || "metadata_only"}
                            />
                            {!p.is_read && (
                              <span className="unread-dot" title="未读" />
                            )}
                          </div>
                          <button
                            className="paper-title"
                            onClick={() => setPaperId(p.id)}
                          >
                            {p.title}
                          </button>
                          {p.assessment ? (
                            <div className="priority-badge">
                              {sort === "priority" && (
                                <strong>#{offset + index + 1} </strong>
                              )}
                              阅读优先分{" "}
                              <strong>{p.assessment.priority_score}</strong> /
                              100 · {p.assessment.topic_name} · 置信度{" "}
                              {confidenceLabel[p.assessment.confidence]}
                            </div>
                          ) : (
                            <div className="muted">待评分 · 不参与推荐排名</div>
                          )}
                          <p className="paper-excerpt">
                            {p.summary ||
                              p.abstract ||
                              "原文已导入，等待解析与阅读。"}
                          </p>
                          <div className="paper-bottom-row">
                            <div className="tags">
                              {p.topics.slice(0, 3).map((t: Obj) => (
                                <span key={t.id} title={t.reason}>
                                  {t.name}
                                </span>
                              ))}
                              {!p.topics.length && <span>未归类</span>}
                            </div>
                            <button
                              className="text-btn"
                              onClick={() => setPaperId(p.id)}
                            >
                              打开论文
                              <ArrowUpRight size={14} />
                            </button>
                          </div>
                        </div>
                        <button
                          className={
                            "icon-btn favorite " + (p.favorite ? "on" : "")
                          }
                          aria-label={"收藏 " + p.title}
                          onClick={() =>
                            action("/papers/" + p.id, "PATCH", {
                              favorite: !p.favorite,
                            })
                          }
                        >
                          <Star
                            size={18}
                            fill={p.favorite ? "currentColor" : "none"}
                          />
                        </button>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="panel library-empty">
                    <Empty
                      title={
                        q || filter || fav || unread || scope || source
                          ? "没有匹配的论文"
                          : "你的下一篇好论文，在这里等你"
                      }
                      action={
                        <button
                          className="btn secondary"
                          onClick={() => setModal("import")}
                        >
                          <Plus size={16} />
                          导入第一篇论文
                        </button>
                      }
                    >
                      {q || filter || fav || unread
                        ? "试试其他关键词，或调整筛选条件。"
                        : "创建主题，让新论文自动入库；也可以从一篇手头的 PDF 开始。"}
                    </Empty>
                  </div>
                )}
                {total > 50 && (
                  <div className="pagination">
                    <button
                      className="btn secondary"
                      disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - 50))}
                    >
                      上一页
                    </button>
                    <span>
                      {offset + 1}–{Math.min(offset + 50, total)} / {total}
                    </span>
                    <button
                      className="btn secondary"
                      disabled={offset + 50 >= total}
                      onClick={() => setOffset(offset + 50)}
                    >
                      下一页
                    </button>
                  </div>
                )}
              </section>
            </>
          )}
          <div className="page-footer">
            <BookOpen size={14} />
            <span>AutoReadPaper · 每一份总结，都有原文可循。</span>
            <span>本地优先，持续积累</span>
          </div>
        </main>
      </div>
      {modal === "cleanup" && (
        <CleanupModal
          topics={topics}
          onClose={() => setModal(null)}
          onSaved={refresh}
          notify={notify}
        />
      )}
      {modal === "topic" && (
        <TopicForm
          initial={edit}
          options={options}
          onClose={() => setModal(null)}
          onSaved={refresh}
          notify={notify}
        />
      )}{" "}
      {modal === "import" && (
        <ImportModal
          topics={topics}
          onClose={() => setModal(null)}
          onSaved={(id) => {
            refresh();
            if (id) {
              setPaperId(id);
              setView("library");
            }
          }}
          notify={notify}
        />
      )}{" "}
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          {toast}
          <button
            className="icon-btn"
            aria-label="关闭提示"
            onClick={() => setToast("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
