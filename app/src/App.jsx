import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookmarkSimple,
  Briefcase,
  CaretDown,
  CaretRight,
  Check,
  CheckCircle,
  CircleNotch,
  FileArrowUp,
  FileText,
  House,
  List,
  MagnifyingGlass,
  Plus,
  SignOut,
  Sparkle,
  User,
  X,
} from "@phosphor-icons/react";
import { api, session } from "./api";

const navigation = [
  ["today", "Today", House],
  ["jobs", "Jobs", Briefcase],
  ["applications", "Applications", FileText],
  ["profile", "Profile", User],
];

function displayDate(value) {
  if (!value) return "Recently updated";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

function firstName(profile) {
  return profile?.name?.trim().split(/\s+/)[0] || "there";
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = await api(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(mode === "register" ? form : { email: form.email, password: form.password }),
      });
      session.set(payload.token);
      onAuthenticated();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-intro">
        <button className="wordmark">Jobert</button>
        <div>
          <p className="eyebrow">Your application workspace</p>
          <h1>Turn promising jobs into stronger applications.</h1>
          <p>Keep your opportunities, CV, profile facts and reviewed answers together—without giving up control of the final submission.</p>
        </div>
        <small>Private by default. Jobert never auto-submits.</small>
      </section>
      <section className="auth-panel">
        <form className="auth-card" onSubmit={submit}>
          <p className="eyebrow">{mode === "login" ? "Welcome back" : "Create your workspace"}</p>
          <h2>{mode === "login" ? "Sign in to Jobert" : "Start using Jobert"}</h2>
          <p>{mode === "login" ? "Pick up where you left off." : "Add your CV and profile after creating your account."}</p>
          {mode === "register" && <label><span>Full name</span><input autoComplete="name" required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>}
          <label><span>Email</span><input type="email" autoComplete="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
          <label><span>Password</span><input type="password" minLength={8} autoComplete={mode === "login" ? "current-password" : "new-password"} required value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button auth-submit" disabled={busy}>{busy ? "One moment…" : mode === "login" ? "Sign in" : "Create account"}<ArrowRight size={18} /></button>
          <button type="button" className="auth-switch" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
            {mode === "login" ? "New to Jobert? Create an account" : "Already have an account? Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

function CompanyLogo({ job, size = 54 }) {
  const knownLogo = { Monzo: "/assets/monzo.png", Stripe: "/assets/stripe.svg", Bloomberg: "/assets/bloomberg.png" }[job.company];
  return (
    <span className={`company-logo ${knownLogo ? "" : "company-logo--letter"}`} style={{ width: size, height: size }} aria-hidden={!knownLogo}>
      {knownLogo ? <img src={knownLogo} alt={`${job.company} logo`} /> : job.company.slice(0, 1).toUpperCase()}
    </span>
  );
}

function ProfileAvatar({ size = 48 }) {
  return <span className="profile-avatar" style={{ width: size, height: size }}><User size={Math.round(size * 0.5)} weight="fill" /></span>;
}

function StatusPill({ children, tone = "blue" }) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}

function EmptyState({ icon: Icon = BookmarkSimple, title, body, action }) {
  return <div className="empty-state"><Icon size={30} /><h3>{title}</h3><p>{body}</p>{action}</div>;
}

function Sidebar({ data, view, onNavigate, mobileOpen, onClose, onLogout }) {
  const profile = data.profile;
  return <>
    <button className={`sidebar-scrim ${mobileOpen ? "is-visible" : ""}`} onClick={onClose} aria-label="Close navigation" />
    <aside className={`sidebar ${mobileOpen ? "is-open" : ""}`}>
      <div className="sidebar-topline"><button className="wordmark" onClick={() => onNavigate("today")}>Jobert</button><button className="icon-button sidebar-close" onClick={onClose} aria-label="Close navigation"><X size={20} /></button></div>
      <nav aria-label="Main navigation">{navigation.map(([key, label, Icon]) => <button key={key} className={`nav-item ${view === key || (view === "review" && key === "applications") ? "is-active" : ""}`} onClick={() => onNavigate(key)}><Icon size={23} weight={view === key ? "fill" : "regular"} /><span>{label}</span></button>)}</nav>
      <div className="sidebar-account">
        <button className="user-card" onClick={() => onNavigate("profile")}><ProfileAvatar /><span><strong>{profile.name}</strong><small>{profile.title || profile.email}</small></span><CaretDown size={16} /></button>
        <button className="logout-button" onClick={onLogout}><SignOut size={17} /> Sign out</button>
      </div>
    </aside>
  </>;
}

function Dashboard({ data, onNavigate, onReview }) {
  const activeApps = data.applications.filter((item) => ["In progress", "Ready to submit"].includes(item.status));
  const activeApp = activeApps[0];
  const activeJob = activeApp && data.jobs.find((job) => job.id === activeApp.job_id);
  const savedJobs = data.jobs.filter((job) => job.saved && job.id !== activeApp?.job_id).slice(0, 3);
  const recent = data.applications.find((item) => !["In progress", "Ready to submit"].includes(item.status));
  const reviewCount = activeApp?.answers.filter((answer) => answer.status !== "accepted").length || 0;
  const submittedThisWeek = data.applications.filter((item) => ["Submitted", "Under review", "Offer"].includes(item.status)).length;

  return <div className="dashboard-grid">
    <section className="dashboard-main">
      <header className="page-heading"><p className="eyebrow">{new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" }).format(new Date())}</p><h1>Good morning, {firstName(data.profile)}</h1><p>Here’s your focus for today.</p></header>
      <section className="dashboard-section">
        <div className="section-heading"><div><h2>Focus Queue <span className="count-badge">{activeApp ? 1 : 0}</span></h2><p>Review and finish your top-priority application.</p></div></div>
        {activeApp && activeJob ? <>
          <button className="focus-row" onClick={() => onReview(activeApp.id)}><CompanyLogo job={activeJob} /><span className="row-copy"><strong>{activeJob.role}</strong><span>{activeJob.company} <b>·</b> {activeJob.location}</span><small>Updated {displayDate(activeApp.updated_at)}</small></span><StatusPill tone={reviewCount ? "blue" : "green"}>{reviewCount ? `${reviewCount} answers to review` : activeApp.status}</StatusPill><CaretRight size={21} /></button>
          <div className="focus-actions"><button className="primary-button" onClick={() => onReview(activeApp.id)}>Continue application <ArrowRight size={18} /></button><button className="text-button" onClick={() => onReview(activeApp.id)}>Review answers <CaretRight size={18} /></button></div>
        </> : <EmptyState icon={Sparkle} title="Your focus queue is clear" body="Prepare a saved job and Jobert will bring the next useful action here." action={<button className="primary-button" onClick={() => onNavigate("jobs")}>Browse jobs <ArrowRight size={18} /></button>} />}
      </section>
      <section className="dashboard-section compact-section"><div className="section-heading"><h2>Saved Jobs <span className="count-badge count-badge--muted">{data.jobs.filter((job) => job.saved).length}</span></h2></div>
        {savedJobs.length ? savedJobs.map((job) => <div className="list-row" key={job.id}><CompanyLogo job={job} size={50} /><span className="row-copy"><strong>{job.role}</strong><span>{job.company} <b>·</b> {job.location}</span><small>{job.season ? `${job.season} intake` : "Saved opportunity"}</small></span><button className="secondary-button" onClick={() => onNavigate("jobs")}>Continue</button><CaretRight size={20} /></div>) : <p className="subtle-copy">Save roles from the Jobs page to keep them close.</p>}
        <button className="inline-link" onClick={() => onNavigate("jobs")}>View all jobs <CaretRight size={18} /></button>
      </section>
      <section className="dashboard-section compact-section"><div className="section-heading"><h2>Recent Applications <span className="count-badge count-badge--muted">{data.applications.length}</span></h2></div>
        {recent ? <div className="list-row"><CompanyLogo job={recent} size={50} /><span className="row-copy"><strong>{recent.role}</strong><span>{recent.company} <b>·</b> {recent.location}</span><small>Updated {displayDate(recent.updated_at)}</small></span><StatusPill tone="green">{recent.status}</StatusPill><CaretRight size={20} /></div> : <p className="subtle-copy">Submitted applications will appear here.</p>}
        <button className="inline-link" onClick={() => onNavigate("applications")}>View all applications <CaretRight size={18} /></button>
      </section>
    </section>
    <aside className="dashboard-aside"><section><h2>This week</h2><div className="stat-row"><CheckCircle size={34} color="#24963f" /><strong>{submittedThisWeek}</strong><span>Applications submitted</span></div><div className="stat-row"><FileText size={34} color="#246bfd" /><strong>{activeApps.length}</strong><span>In progress</span></div><div className="stat-row"><BookmarkSimple size={34} /><strong>{data.jobs.filter((job) => job.saved).length}</strong><span>Saved jobs</span></div></section>
      <section className="tips-section"><h2>Good next moves</h2>{[["Keep your CV current", data.profile.cv ? `Using ${data.profile.cv.filename}` : "Upload a PDF so answers can use your evidence."], ["Complete your profile", "Accurate facts make every draft safer and more useful."], ["Review before submitting", "Jobert prepares; you always make the final call."]].map(([title, copy]) => <button className="tip-row" key={title} onClick={() => onNavigate("profile")}><CheckCircle size={18} color="#24963f" /><span><strong>{title}</strong><small>{copy}</small></span><CaretRight size={18} /></button>)}</section>
      <section className="matches-section"><h2>Your matches</h2><p>Skills Jobert uses for ranking</p><div className="skill-list">{data.profile.skills.length ? data.profile.skills.map((skill) => <span key={skill}>{skill}</span>) : <small className="subtle-copy">Add skills to improve matching.</small>}</div><button className="inline-link" onClick={() => onNavigate("profile")}>Update skills in profile <CaretRight size={18} /></button></section>
    </aside>
  </div>;
}

function JobsView({ data, setData, onReview, notify }) {
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(30);
  const [busyId, setBusyId] = useState("");
  const filtered = data.jobs.filter((job) => `${job.role} ${job.company} ${job.location}`.toLowerCase().includes(query.toLowerCase()));
  const visible = filtered.slice(0, visibleCount);

  async function toggleSaved(job) {
    const saved = !job.saved;
    setData((current) => ({ ...current, jobs: current.jobs.map((item) => item.id === job.id ? { ...item, saved } : item) }));
    try { await api(`/jobs/${job.id}/saved`, { method: "PATCH", body: JSON.stringify({ saved }) }); notify(saved ? "Job saved" : "Removed from saved jobs"); }
    catch (error) { setData((current) => ({ ...current, jobs: current.jobs.map((item) => item.id === job.id ? { ...item, saved: !saved } : item) })); notify(error.message, true); }
  }

  async function prepare(job) {
    setBusyId(job.id);
    try {
      const application = await api("/applications", { method: "POST", body: JSON.stringify({ jobId: job.id }) });
      setData((current) => ({ ...current, jobs: current.jobs.map((item) => item.id === job.id ? { ...item, saved: true, application_id: application.id } : item), applications: [application, ...current.applications.filter((item) => item.id !== application.id)] }));
      notify("Application workspace prepared");
      onReview(application.id);
    } catch (error) { notify(error.message, true); }
    finally { setBusyId(""); }
  }

  return <div className="standard-page"><header className="standard-header"><div><p className="eyebrow">{data.jobs.length} live opportunities</p><h1>Jobs</h1><p>Keep promising roles together and prepare when you’re ready.</p></div></header>
    <label className="search-field"><MagnifyingGlass size={20} /><span className="sr-only">Search jobs</span><input value={query} onChange={(event) => { setQuery(event.target.value); setVisibleCount(30); }} placeholder="Search role, company or location" /></label>
    <div className="job-list">{visible.length ? visible.map((job) => <article className="job-row" key={job.id}><CompanyLogo job={job} size={56} /><div className="job-row-main"><span className="match-label">{job.match}% profile match</span><h2>{job.role}</h2><p>{job.company} · {job.location}{job.season && ` · ${job.season}`}</p><small>{job.summary || `A ${job.categories?.join(", ") || "technology"} opportunity listed by ${job.company}.`}</small></div><div className="job-row-actions"><button className="icon-button" onClick={() => toggleSaved(job)} aria-label={job.saved ? `Remove ${job.role} from saved jobs` : `Save ${job.role}`}><BookmarkSimple size={22} weight={job.saved ? "fill" : "regular"} /></button>{job.application_id ? <button className="primary-button small-button" onClick={() => onReview(job.application_id)}>Continue</button> : <button className="secondary-button" disabled={busyId === job.id} onClick={() => prepare(job)}>{busyId === job.id ? "Preparing…" : "Prepare"}</button>}<a className="external-link" href={job.link} target="_blank" rel="noreferrer" aria-label={`Open ${job.role} listing`}><ArrowRight size={18} /></a></div></article>) : <EmptyState title="No jobs match that search" body="Try a company, role, skill, or location." />}</div>
    {visibleCount < filtered.length && <button className="secondary-button load-more" onClick={() => setVisibleCount((count) => count + 30)}>Show more jobs ({filtered.length - visibleCount} remaining)</button>}
  </div>;
}

function ApplicationsView({ data, onReview }) {
  const [filter, setFilter] = useState("All");
  const options = ["All", "In progress", "Submitted"];
  const filtered = data.applications.filter((application) => filter === "All" || (filter === "Submitted" ? !["In progress", "Ready to submit"].includes(application.status) : ["In progress", "Ready to submit"].includes(application.status)));
  return <div className="standard-page"><header className="standard-header"><div><p className="eyebrow">Your application history</p><h1>Applications</h1><p>See what needs attention and what has already moved forward.</p></div></header><div className="filter-tabs" role="tablist" aria-label="Application status filter">{options.map((option) => <button key={option} role="tab" aria-selected={filter === option} className={filter === option ? "is-active" : ""} onClick={() => setFilter(option)}>{option}</button>)}</div><div className="application-table">{filtered.length ? filtered.map((application) => { const remaining = application.answers.filter((answer) => answer.status !== "accepted").length; return <button className="application-row" key={application.id} onClick={() => onReview(application.id)}><CompanyLogo job={application} size={50} /><span className="row-copy"><strong>{application.role}</strong><span>{application.company} · {application.location}</span><small>Updated {displayDate(application.updated_at)}</small></span>{remaining ? <StatusPill>{remaining} to review</StatusPill> : <StatusPill tone="green">{application.status}</StatusPill>}<CaretRight size={20} /></button>; }) : <EmptyState icon={FileText} title="No applications here yet" body="Prepare a job to start a grounded application workspace." />}</div></div>;
}

function ProfileView({ data, setData, notify }) {
  const [draft, setDraft] = useState(data.profile);
  const [newSkill, setNewSkill] = useState("");
  const [aiKey, setAiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const fileInput = useRef(null);
  useEffect(() => setDraft(data.profile), [data.profile]);

  async function saveProfile(event) {
    event.preventDefault(); setSaving(true);
    try { const profile = await api("/profile", { method: "PATCH", body: JSON.stringify({ ...draft, ...(aiKey.trim() ? { geminiApiKey: aiKey.trim() } : {}) }) }); setData((current) => ({ ...current, profile })); setAiKey(""); notify("Profile saved"); }
    catch (error) { notify(error.message, true); }
    finally { setSaving(false); }
  }
  function addSkill() { const value = newSkill.trim(); if (!value || draft.skills.includes(value)) return; setDraft((current) => ({ ...current, skills: [...current.skills, value] })); setNewSkill(""); }
  async function uploadCv(event) {
    const file = event.target.files?.[0]; if (!file) return;
    const body = new FormData(); body.append("file", file);
    try { const cv = await api("/profile/cv", { method: "POST", body }); setData((current) => ({ ...current, profile: { ...current.profile, cv } })); setDraft((current) => ({ ...current, cv })); notify("CV uploaded and indexed"); }
    catch (error) { notify(error.message, true); }
    finally { event.target.value = ""; }
  }

  return <div className="standard-page profile-page"><header className="standard-header"><div><p className="eyebrow">The facts Jobert can use</p><h1>Your profile</h1><p>Keep this accurate; every suggested answer is grounded here.</p></div></header><form onSubmit={saveProfile}>
    <section className="profile-section profile-intro"><ProfileAvatar size={68} /><div><h2>{draft.name}</h2><p>{draft.title || "Add your current title"} · {draft.location || "Add your location"}</p><button type="button" className="text-button" onClick={() => fileInput.current?.click()}>{draft.cv ? "Replace CV" : "Upload CV"}</button><input ref={fileInput} className="sr-only" type="file" accept="application/pdf,.pdf" onChange={uploadCv} /></div><StatusPill tone={draft.cv ? "green" : "blue"}>{draft.cv ? draft.cv.filename : "CV needed"}</StatusPill></section>
    <section className="profile-section"><h2>Essential details</h2><div className="field-grid">{[["name", "Full name"], ["title", "Current title"], ["email", "Email"], ["location", "Location"], ["workAuthorisation", "Work authorisation"]].map(([key, label]) => <label key={key}><span>{label}</span><input disabled={key === "email"} value={draft[key] || ""} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} /></label>)}</div></section>
    <section className="profile-section"><h2>Skills</h2><p className="section-description">These help Jobert rank roles and tailor evidence.</p><div className="editable-skills">{draft.skills.map((skill) => <span key={skill}>{skill}<button type="button" aria-label={`Remove ${skill}`} onClick={() => setDraft({ ...draft, skills: draft.skills.filter((item) => item !== skill) })}><X size={14} /></button></span>)}</div><div className="add-skill"><label><span className="sr-only">New skill</span><input value={newSkill} onChange={(event) => setNewSkill(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addSkill(); } }} placeholder="Add a skill" /></label><button type="button" className="secondary-button" onClick={addSkill}><Plus size={17} /> Add</button></div></section>
    <section className="profile-section"><h2>AI answer drafting</h2><p className="section-description">Optional. Add your Gemini API key to create CV-grounded drafts; the key is encrypted before storage.</p><label className="integration-field"><span>{draft.aiConfigured ? "Gemini is connected" : "Gemini API key"}</span><input type="password" autoComplete="off" value={aiKey} onChange={(event) => setAiKey(event.target.value)} placeholder={draft.aiConfigured ? "Enter a new key to replace it" : "Paste your Gemini API key"} /></label></section>
    <button className="primary-button" disabled={saving} type="submit">{saving ? "Saving…" : "Save profile"} <Check size={18} /></button>
  </form></div>;
}

function ReviewView({ data, applicationId, setData, onBack, notify }) {
  const application = data.applications.find((item) => item.id === applicationId);
  const [selectedId, setSelectedId] = useState(application?.answers.find((answer) => answer.status !== "accepted")?.id || application?.answers[0]?.id);
  const [showReady, setShowReady] = useState(false);
  useEffect(() => { if (application && !application.answers.some((item) => item.id === selectedId)) setSelectedId(application.answers[0]?.id); }, [application, selectedId]);
  if (!application) return null;
  const selected = application.answers.find((answer) => answer.id === selectedId) || application.answers[0];
  const accepted = application.answers.filter((answer) => answer.status === "accepted").length;
  const ready = accepted === application.answers.length && application.answers.length > 0;

  function updateLocal(answerId, changes) { setData((current) => ({ ...current, applications: current.applications.map((app) => app.id !== application.id ? app : { ...app, answers: app.answers.map((answer) => answer.id === answerId ? { ...answer, ...changes } : answer) }) })); }
  async function persist(answerId, changes) { try { await api(`/applications/${application.id}/answers/${answerId}`, { method: "PATCH", body: JSON.stringify(changes) }); } catch (error) { notify(error.message, true); } }
  async function acceptAnswer() { updateLocal(selected.id, { status: "accepted" }); await persist(selected.id, { value: selected.value, status: "accepted" }); const next = application.answers.find((answer) => answer.id !== selected.id && answer.status !== "accepted"); if (next) setSelectedId(next.id); notify("Answer accepted"); }
  async function prepareFill() { if (!ready) { notify(`${application.answers.length - accepted} answers still need review`, true); return; } try { await api(`/applications/${application.id}/status`, { method: "PATCH", body: JSON.stringify({ status: "Ready to submit" }) }); setData((current) => ({ ...current, applications: current.applications.map((app) => app.id === application.id ? { ...app, status: "Ready to submit", updated_at: new Date().toISOString() } : app) })); setShowReady(true); } catch (error) { notify(error.message, true); } }
  async function markSubmitted() { try { await api(`/applications/${application.id}/status`, { method: "PATCH", body: JSON.stringify({ status: "Submitted" }) }); setData((current) => ({ ...current, applications: current.applications.map((app) => app.id === application.id ? { ...app, status: "Submitted", updated_at: new Date().toISOString() } : app) })); setShowReady(false); onBack(); notify("Application marked submitted"); } catch (error) { notify(error.message, true); } }

  return <div className="review-page"><header className="review-header"><button className="text-button" onClick={onBack}><ArrowLeft size={18} /> Back</button><span><strong>{application.role}</strong><small>{application.company} · {application.location}</small></span><div className="review-progress"><strong>{accepted} of {application.answers.length} ready</strong><div><span style={{ width: `${application.answers.length ? (accepted / application.answers.length) * 100 : 0}%` }} /></div></div></header><div className="review-layout"><aside className="question-list"><h2>Application questions <span>{application.answers.length}</span></h2>{application.answers.map((answer, index) => <button className={answer.id === selected.id ? "is-active" : ""} key={answer.id} onClick={() => setSelectedId(answer.id)}><b>{index + 1}</b><span><strong>{answer.question}</strong><small className={answer.status === "accepted" ? "accepted" : "review"}>{answer.status === "accepted" ? <CheckCircle weight="fill" /> : <CircleNotch weight="fill" />}{answer.status === "accepted" ? "Accepted" : "Needs review"}</small></span><CaretRight size={17} /></button>)}</aside>
    <main className="answer-editor"><p className="eyebrow">Question {application.answers.findIndex((item) => item.id === selected.id) + 1} of {application.answers.length}</p><h1>{selected.question}</h1><p>Review the suggested answer. Edit it so it sounds like you and stays accurate.</p><label><span>Your answer</span><textarea value={selected.value} onChange={(event) => updateLocal(selected.id, { value: event.target.value, status: "review" })} onBlur={() => persist(selected.id, { value: selected.value, status: selected.status })} /></label><div className="source-box"><Sparkle size={20} /><span><strong>Why this answer?</strong><small>Grounded in {selected.source}. Jobert never invents missing experience.</small></span></div><div className="editor-actions"><button className="secondary-button" onClick={() => { persist(selected.id, { value: selected.value, status: selected.status }); notify("Saved for later"); }}>Skip for now</button><button className="primary-button" onClick={acceptAnswer}>Accept answer <Check size={18} /></button></div></main></div>
    <footer className="review-footer"><span><CheckCircle size={20} /> Your data stays private and you remain in control.</span><button className={`fill-button ${ready ? "is-ready" : ""}`} onClick={prepareFill}>Prepare accepted answers ({accepted}) <ArrowRight size={19} /></button></footer>
    {showReady && <div className="modal-layer"><div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="ready-title"><CheckCircle className="modal-icon" size={44} weight="fill" /><h2 id="ready-title">Your answers are ready</h2><p>Open the original job form, paste or fill the accepted answers, and review everything once more before you submit.</p><div className="modal-actions"><button className="secondary-button" onClick={() => setShowReady(false)}>Keep reviewing</button><a className="primary-button" href={application.link} target="_blank" rel="noreferrer">Open job form <ArrowRight size={18} /></a><button className="primary-button quiet-primary" onClick={markSubmitted}>Mark submitted</button></div></div></div>}
  </div>;
}

export function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(session.get()));
  const [view, setView] = useState("today");
  const [applicationId, setApplicationId] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [toast, setToast] = useState({ message: "", error: false });

  async function load() {
    if (!session.get()) { setData(null); setLoading(false); return; }
    setLoading(true);
    try { setData(await api("/bootstrap")); }
    catch { session.clear(); setData(null); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!toast.message) return undefined; const id = setTimeout(() => setToast({ message: "", error: false }), 2800); return () => clearTimeout(id); }, [toast]);
  const title = useMemo(() => navigation.find(([key]) => key === view)?.[1] || "Application review", [view]);
  useEffect(() => { document.title = `${title} · Jobert`; }, [title]);
  function notify(message, error = false) { setToast({ message, error }); }
  function navigate(next) { setView(next); setMobileOpen(false); }
  function review(id) { setApplicationId(id); setView("review"); setMobileOpen(false); }
  async function logout() { try { await api("/auth/logout", { method: "POST" }); } catch { /* Local logout must still succeed. */ } session.clear(); setData(null); setView("today"); }

  if (loading) return <div className="loading-screen"><span className="wordmark">Jobert</span><CircleNotch size={28} className="spinner" /></div>;
  if (!data) return <AuthScreen onAuthenticated={load} />;
  return <div className="app-shell">{view !== "review" && <Sidebar data={data} view={view} onNavigate={navigate} mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} onLogout={logout} />}<div className={view === "review" ? "review-shell" : "content-shell"}>{view !== "review" && <header className="mobile-header"><button className="icon-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><List size={24} /></button><button className="wordmark" onClick={() => navigate("today")}>Jobert</button><ProfileAvatar size={34} /></header>}{view === "today" && <Dashboard data={data} onNavigate={navigate} onReview={review} />}{view === "jobs" && <JobsView data={data} setData={setData} onReview={review} notify={notify} />}{view === "applications" && <ApplicationsView data={data} onReview={review} />}{view === "profile" && <ProfileView data={data} setData={setData} notify={notify} />}{view === "review" && <ReviewView data={data} applicationId={applicationId} setData={setData} onBack={() => navigate("today")} notify={notify} />}</div><div className={`toast ${toast.message ? "is-visible" : ""} ${toast.error ? "is-error" : ""}`} role="status" aria-live="polite">{toast.error ? <X size={20} /> : <CheckCircle size={20} weight="fill" />} {toast.message}</div></div>;
}
