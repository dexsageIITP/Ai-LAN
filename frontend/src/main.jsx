import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { CircleMarker, MapContainer, Marker, Popup, TileLayer, useMapEvents } from "react-leaflet";
import { Activity, AlertTriangle, BarChart3, Bell, CheckCircle2, ChevronRight, CircleDot, ExternalLink, FileText, Filter, Flag, Gauge, Landmark, LifeBuoy, LogOut, Mail, MapPin, Menu, Phone, Plus, Search, ShieldCheck, Sparkles, Upload, UserRound, X } from "lucide-react";
import "./styles.css";
import "leaflet/dist/leaflet.css";

const API = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000/api`;
const labels = { roads:"Roads", water_supply:"Water Supply", drainage:"Drainage", waste_management:"Waste Management", public_lighting:"Public Lighting", public_infrastructure:"Public Infrastructure", waterlogging:"Waterlogging", environment:"Environment", other:"Other" };
const severityColors = { low:"#4fae7b", medium:"#e2a62d", high:"#e26d42", critical:"#c84156" };
const statusLabels = { submitted:"Submitted", processing:"Processing", authority_verification_pending:"Authority review", notification_pending:"Notification pending", notification_sent:"Notification sent", under_review:"Under review", assigned:"Assigned", in_progress:"In progress", resolved:"Resolved", rejected:"Rejected", closed:"Closed", manual_review:"Manual review" };
const titleCase = value => value.replace(/\b\w/g, character => character.toUpperCase());

async function request(path, options = {}) { const token = localStorage.getItem("ailan-token"); const headers = new Headers(options.headers || {}); if (token) headers.set("Authorization", `Bearer ${token}`); const response = await fetch(API + path, {...options, headers}); if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || "Request failed"); } return response.json(); }

function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState(""), [password, setPassword] = useState(""), [name, setName] = useState(""), [role, setRole] = useState("citizen"), [signup, setSignup] = useState(false), [error, setError] = useState(""), [googleId, setGoogleId] = useState("");
  useEffect(() => {
    request("/auth/google-config").then(({ client_id }) => {
      setGoogleId(client_id);
      if (!client_id) return;
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true; script.defer = true;
      script.onload = () => {
        window.google?.accounts.id.initialize({
          client_id,
          callback: response => request("/auth/google", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({credential:response.credential}) }).then(onLogin).catch(err => setError(err.message)),
        });
      };
      script.onerror = () => setError("Google Sign-In could not load. Check your network connection or browser extensions.");
      document.head.appendChild(script);
      return () => script.remove();
    }).catch(() => setError("Unable to load sign-in configuration"));
  }, [onLogin]);
  useEffect(() => {
    if (googleId && window.google?.accounts?.id) window.google.accounts.id.renderButton(document.getElementById("google-button"), { theme:"outline", size:"large", width:320, text:"continue_with" });
  }, [googleId]);
  const submit = e => {
    e.preventDefault(); setError("");
    const path = signup ? "/auth/register" : "/auth/login";
    request(path, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ email, password, role, ...(signup ? {name} : {}) }) }).then(onLogin).catch(err => setError(err.message));
  };
  return <div className="auth-page"><div className="auth-card"><div className="auth-brand"><div className="brand-mark"><Sparkles size={20}/></div><b>Ai-LAN</b></div><span className="eyebrow accent">CIVIC INTELLIGENCE PLATFORM</span><h2>{signup ? "Create your account" : "Welcome back"}</h2><p className="muted">{signup ? "Join your community and make local issues visible." : "Sign in to report issues and track your complaints."}</p>{error && <div className="auth-error"><AlertTriangle size={15}/>{error}</div>}<div id="google-button" className="google-button">{!googleId && "Google Sign-In is not configured"}</div><div className="auth-divider"><span>or continue with email</span></div><form onSubmit={submit}>{signup && <input required placeholder="Your name" value={name} onChange={e=>setName(e.target.value)}/>}<label className="role-label">Account type<select value={role} onChange={e=>setRole(e.target.value)}><option value="citizen">Citizen</option><option value="government">Government</option><option value="admin">Admin</option></select></label><input required type="email" placeholder="Email address" value={email} onChange={e=>setEmail(e.target.value)}/><input required minLength="8" type="password" placeholder="Password (8+ characters)" value={password} onChange={e=>setPassword(e.target.value)}/><button className="primary auth-submit">{signup ? "Create account" : "Sign in"} <ChevronRight size={17}/></button></form><button className="auth-switch" onClick={()=>{setSignup(!signup);setError("")}}>{signup ? "Already have an account? Sign in" : "New to Ai-LAN? Create an account"}</button><small className="privacy"><ShieldCheck size={13}/> Independent civic reporting platform</small></div></div>;
}

function App() {
  const [user, setUser] = useState(() => { try { return JSON.parse(localStorage.getItem("ailan-user")); } catch { return null; } }), [page, setPage] = useState("Overview"), [mobileNav, setMobileNav] = useState(false), [issues, setIssues] = useState([]), [analytics, setAnalytics] = useState(null), [health, setHealth] = useState(null), [selected, setSelected] = useState(null), [query, setQuery] = useState(""), [filter, setFilter] = useState("all"), [showReport, setShowReport] = useState(false), [notice, setNotice] = useState("");
  const mainRef = useRef(null);
  const handleLogin = data => { localStorage.setItem("ailan-user", JSON.stringify(data.user)); localStorage.setItem("ailan-token", data.token); setUser(data.user); };
  const refresh = () => Promise.all([request("/issues"), request("/analytics"), request("/health")]).then(([i,a,h]) => { setIssues(i); setAnalytics(a); setHealth(h); return i; }).catch(e => { setNotice(e.message); throw e; });
  const handleReportSaved = async report => {
    setIssues(current => [report, ...current.filter(issue => issue.id !== report.id)]);
    setShowReport(false);
    setPage("My Complaints");
    setNotice(report.ai_status === "completed" ? "Report saved and AI analysis completed." : "Report saved; AI analysis requires manual review.");
    try {
      await refresh();
    } catch {
      setIssues(current => [report, ...current.filter(issue => issue.id !== report.id)]);
    }
  };
  useEffect(() => { refresh(); }, []);
  useEffect(() => { mainRef.current?.scrollTo({ top: 0, behavior: "auto" }); }, [page]);
  const visible = useMemo(() => issues.filter(i => (filter === "all" || i.category === filter) && `${i.title} ${i.location_text}`.toLowerCase().includes(query.toLowerCase())), [issues, filter, query]);
  if (!user) return <LoginScreen onLogin={handleLogin}/>;
  return <div className="app">
    <aside className={"sidebar "+(mobileNav?"mobile-open":"")}><div className="brand"><div className="brand-mark"><Sparkles size={20}/></div><div><b>Ai-LAN</b><small>Civic intelligence</small></div><button className="mobile-close" onClick={()=>setMobileNav(false)}><X size={18}/></button></div>
      <nav>{[["Overview",Gauge],["Live Civic Map",MapPin],["My Complaints",FileText],...(user.role==="government"||user.role==="admin"?[["Authority Directory",Landmark]]:[]),...(user.role==="admin"?[["Analytics",BarChart3]]:[])].map(([name,Icon]) => <button className={page===name?"active":""} onClick={()=>{setPage(name);setMobileNav(false)}} key={name}><Icon size={18}/>{name}</button>)}</nav>
      <div className="sidebar-bottom"><div className="demo-card"><div className="eyebrow"><CircleDot size={13}/> {health?.demo_mode?"DEMONSTRATION MODE":"LIVE SITE MODE"}</div><p>{health?.demo_mode?"Sample records are clearly labelled. External services are optional.":"Live integrations are configured through the backend."}</p><span className={health?.database_connected?"online":"offline"}><span/> System operational</span></div><button className="profile" onClick={()=>setPage("My Profile")}><div className="avatar">{(user.name||user.email).slice(0,2).toUpperCase()}</div><div><b>{user.name}</b><small>{user.email}</small></div><ChevronRight size={16}/></button></div>
    </aside>
    <main ref={mainRef}><header><button className="mobile-menu" onClick={()=>setMobileNav(true)}><Menu size={20}/></button><div><span className="eyebrow">INDEPENDENT CIVIC REPORTING PLATFORM</span><h1>{page}</h1></div><div className="header-actions"><button className="icon-btn"><Bell size={19}/><i/></button><button className="user-avatar" onClick={()=>setPage("My Profile")}>{(user.name||user.email).slice(0,2).toUpperCase()}</button></div></header>
      {mobileNav && <button className="nav-backdrop" aria-label="Close navigation" onClick={()=>setMobileNav(false)}/>}
      {notice && <div className="notice"><AlertTriangle size={17}/>{notice}<button onClick={()=>setNotice("")}><X size={15}/></button></div>}
      {page==="Overview" && <Overview analytics={analytics} issues={issues} onOpen={setSelected} onReport={()=>setShowReport(true)} />}
      {page==="Live Civic Map" && <MapPage issues={visible} query={query} setQuery={setQuery} filter={filter} setFilter={setFilter} onOpen={setSelected} onReport={()=>setShowReport(true)} />}
      {page==="My Complaints" && <Complaints issues={issues} onOpen={setSelected} onReport={()=>setShowReport(true)} />}
      {page==="Analytics" && <Analytics analytics={analytics} />}
      {page==="Authority Directory" && <Authorities />}
      {page==="My Profile" && <Profile user={user} onLogout={()=>{localStorage.removeItem("ailan-user");localStorage.removeItem("ailan-token");setUser(null)}} />}
    </main>
    {selected && <IssuePanel issue={selected} user={user} onClose={()=>setSelected(null)} onUpdated={refresh}/>}
    {showReport && <ReportModal onClose={()=>setShowReport(false)} onDone={handleReportSaved} onError={setNotice}/>}
  </div>;
}

function Profile({ user, onLogout }) {
  const initials = (user.name || user.email).slice(0, 2).toUpperCase();
  return <section className="content"><div className="profile-hero"><div className="profile-large-avatar">{initials}</div><div><span className="eyebrow accent">ACCOUNT SETTINGS</span><h2>{user.name}</h2><p>{user.email}</p></div></div><div className="profile-grid"><div className="card profile-details"><div className="profile-section-title"><UserRound size={18}/><h3>Personal information</h3></div><label>Full name<input value={user.name} readOnly/></label><label>Email address<input value={user.email} readOnly/></label><label>Account type<input value={user.role === "admin" ? "Platform administrator" : user.role === "government" ? "Government user" : "Citizen"} readOnly/></label></div><div className="card profile-details"><div className="profile-section-title"><ShieldCheck size={18}/><h3>Privacy & access</h3></div><p className="profile-copy">Your contact details are private and are not shown on the public civic map. You decide when information is shared with an authority.</p><div className="profile-status"><CheckCircle2 size={17}/><span><b>Account protected</b><small>Secure session is active</small></span></div><button className="logout-btn" onClick={onLogout}><LogOut size={16}/> Sign out</button></div></div></section>
}

function OverviewMap({issues,onOpen}) { return <div className="overview-map card"><div className="overview-map-heading"><div><span className="eyebrow">LIVE CIVIC MAP</span><h3>Problems reported across the city</h3></div><span>{issues.length} reports</span></div><div className="overview-map-frame"><MapContainer center={[25.6093,85.1376]} zoom={13} scrollWheelZoom className="leaflet-map"><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>{issues.map(i=><CircleMarker key={i.id} center={[i.latitude,i.longitude]} radius={9} pathOptions={{color:"#fff",weight:2,fillColor:severityColors[i.severity],fillOpacity:.95}} eventHandlers={{click:()=>onOpen(i)}}><Popup><b>{titleCase(i.title)}</b><br/>{statusLabels[i.status]||i.status}</Popup></CircleMarker>)}</MapContainer></div></div> }
function Overview({ analytics, issues, onOpen, onReport }) { return <section className="content"><div className="hero"><div><span className="eyebrow accent">GOOD AFTERNOON, CITIZEN</span><h2>Make your city<br/><em>more responsive.</em></h2><p>See what needs attention nearby, report a civic issue, and follow it through to resolution.</p><button className="primary" onClick={onReport}><Plus size={18}/> Report an issue</button></div><div className="hero-art"><div className="pulse p1"/><div className="pulse p2"/><MapPin size={42}/><span>Live civic pulse</span></div></div><div className="stats">{[["Total reports",analytics?.total||0,Activity,"teal"],["Needs attention",analytics?.pending||0,AlertTriangle,"orange"],["High priority",analytics?.high_priority||0,Flag,"red"],["Resolved",analytics?.resolved||0,CheckCircle2,"green"]].map(([label,value,Icon,color])=><div className="stat" key={label}><div className={"stat-icon "+color}><Icon size={18}/></div><div><small>{label}</small><strong>{value}</strong><span>{label==="Resolved"?"Across all reports":"Current snapshot"}</span></div></div>)}</div><OverviewMap issues={issues} onOpen={onOpen}/><div className="section-heading"><div><span className="eyebrow">FIELD REPORTS</span><h3>Recent civic activity</h3></div><button className="text-btn" onClick={()=>issues[0]&&onOpen(issues[0])}>View all <ChevronRight size={15}/></button></div><div className="report-list">{issues.slice(0,4).map(i=><ReportRow key={i.id} issue={i} onClick={()=>onOpen(i)}/>)}</div></section> }
function MapPage({issues,query,setQuery,filter,setFilter,onOpen,onReport}) { return <section className="content"><div className="map-toolbar"><div className="search"><Search size={17}/><input placeholder="Search reports or localities" value={query} onChange={e=>setQuery(e.target.value)}/></div><select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All categories</option>{Object.entries(labels).map(([v,l])=><option value={v} key={v}>{l}</option>)}</select><button className="primary compact" onClick={onReport}><Plus size={17}/> Report issue</button></div><div className="map-layout"><div className="map"><MapContainer center={[25.6093,85.1376]} zoom={13} scrollWheelZoom className="leaflet-map"><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>{issues.map(i=><CircleMarker key={i.id} center={[i.latitude,i.longitude]} radius={9} pathOptions={{color:"#fff",weight:2,fillColor:severityColors[i.severity],fillOpacity:.95}} eventHandlers={{click:()=>onOpen(i)}}><Popup><b>{i.title}</b><br/>{statusLabels[i.status]}</Popup></CircleMarker>)}</MapContainer><div className="map-overlay"><b>Patna civic pulse</b><span>{issues.length} reports in view</span></div><div className="legend">{Object.entries(severityColors).map(([k,c])=><span key={k}><i style={{background:c}}/>{k}</span>)}</div></div><div className="map-list"><div className="list-title"><span><b>Reports nearby</b><small>{issues.length} results</small></span><Filter size={17}/></div>{issues.map(i=><ReportRow key={i.id} issue={i} onClick={()=>onOpen(i)}/>)}</div></div></section> }
function Complaints({issues,onOpen,onReport}) { return <section className="content"><div className="page-intro"><div><span className="eyebrow">YOUR REPORTS</span><h2>Complaint tracking</h2><p>Follow updates from submission through authority action.</p></div><button className="primary" onClick={onReport}><Plus size={18}/> Report an issue</button></div><div className="report-list full">{issues.map(i=><ReportRow key={i.id} issue={i} onClick={()=>onOpen(i)}/>)}</div></section> }
function Analytics({analytics}) { return <section className="content"><div className="page-intro"><div><span className="eyebrow">CIVIC INTELLIGENCE</span><h2>Patterns that matter</h2><p>Insights calculated from stored civic reports.</p></div></div><div className="analytics-grid"><div className="card chart"><h3>Reports by category</h3>{Object.entries(analytics?.category||{}).map(([k,v])=><div className="bar-row" key={k}><span>{labels[k]||k}</span><div><i style={{width:`${Math.max(14,v/(analytics?.total||1)*100)}%`}}/></div><b>{v}</b></div>)}</div><div className="card chart"><h3>Severity distribution</h3>{Object.entries(analytics?.severity||{}).map(([k,v])=><div className="severity-row" key={k}><i style={{background:severityColors[k]}}/><span>{k}</span><b>{v}</b><small>{Math.round(v/(analytics?.total||1)*100)}%</small></div>)}</div></div></section> }
function Authorities() { const [data,setData]=useState([]); useEffect(()=>{request("/authorities").then(setData)},[]); return <section className="content"><div className="page-intro"><div><span className="eyebrow">VERIFIED DIRECTORY</span><h2>Authority contacts</h2><p>Grounded contact information for responsible departments.</p></div></div><div className="authority-grid">{data.map(a=><div className="card authority" key={a.id}><div className="authority-top"><div className="authority-icon"><Landmark size={21}/></div><span className="verified"><ShieldCheck size={14}/> Verified</span></div><h3>{a.name}</h3><p>{a.department} · {a.jurisdiction}</p><div className="contact"><span><Bell size={15}/>{a.phone_number||"Contact number unavailable"}</span><span><FileText size={15}/>{a.official_email||"Email unavailable"}</span><span><MapPin size={15}/>{a.address||"Address unavailable"}</span></div><small className="sample-note">Demonstration record · Last verified {a.last_verified_at?.slice(0,10)}</small></div>)}</div></section> }
function ReportRow({issue,onClick}) { return <button className="report-row" onClick={onClick}><div className="issue-icon" style={{color:severityColors[issue.severity]}}><MapPin size={19}/></div><div className="row-main"><div><b>{titleCase(issue.title)}</b><span className="pill" style={{color:severityColors[issue.severity],background:`${severityColors[issue.severity]}18`}}>{issue.severity}</span></div><p>{issue.description}</p><small><MapPin size={12}/>{issue.location_text||`${issue.latitude.toFixed(3)}, ${issue.longitude.toFixed(3)}`} · {labels[issue.category]||titleCase(issue.category.replace("_"," "))}</small></div><div className="row-status"><span className={"status-dot "+issue.status}/>{statusLabels[issue.status]||issue.status}<ChevronRight size={16}/></div></button> }
function IssuePanel({issue,user,onClose,onUpdated}) {
  const [history,setHistory]=useState([]), [status,setStatus]=useState(issue.status), [liveOffice,setLiveOffice]=useState(null), [officeError,setOfficeError]=useState(""), [address,setAddress]=useState("");
  useEffect(()=>{request(`/issues/${issue.report_number}/history`).then(setHistory)},[issue.report_number]);
  useEffect(()=>{request(`/issues/${issue.report_number}/office`).then(setLiveOffice).catch(error=>setOfficeError(error.message))},[issue.report_number]);
  useEffect(()=>{
    request(`/geocode/reverse?latitude=${issue.latitude}&longitude=${issue.longitude}`)
      .then(result=>setAddress(result.address))
      .catch(()=>setAddress(
        issue.location_text && !["Map-selected location","Device location"].includes(issue.location_text)
          ? issue.location_text
          : "Address unavailable; coordinates shown below"
      ));
  },[issue.location_text,issue.latitude,issue.longitude]);
  const authority=liveOffice||issue.authority;
  const hasVerifiedEmail=Boolean(authority?.official_email);
  const directionsUrl=authority?.address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(authority.address)}` : null;
  const aiSummary=issue.ai_summary||"AI analysis is not available for this report.";
  const update=()=>request(`/issues/${issue.report_number}/status`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})}).then(onUpdated);
  const canUpdateStatus=user?.role==="government"||user?.role==="admin";
  return <div className="drawer-backdrop" onClick={onClose}><aside className="drawer" onClick={e=>e.stopPropagation()}><button className="close" onClick={onClose}><X size={19}/></button><span className="eyebrow">REPORT {issue.report_number}</span><h2>{titleCase(issue.title)}</h2><div className="drawer-pills"><span className="pill" style={{color:severityColors[issue.severity],background:`${severityColors[issue.severity]}18`}}>{issue.severity} priority</span><span className="pill neutral">{statusLabels[issue.status]}</span></div><p className="drawer-description">{issue.description}</p><div className="detail-block"><span><Sparkles size={16}/> AI analysis</span><b>{aiSummary}<small>{issue.ai_status==="completed"?"Generated from the report image and description.":"Manual review required."}</small></b></div><div className="detail-block"><span><MapPin size={16}/> Address</span><b>{address||"Finding address..."}<small>{issue.latitude.toFixed(5)}, {issue.longitude.toFixed(5)}</small></b></div><div className="detail-block"><span><Landmark size={16}/> Responsible authority</span><b>{authority?.name||"Being verified"}{directionsUrl && <a className="directions-link" href={directionsUrl} target="_blank" rel="noreferrer">Get directions <ExternalLink size={12}/></a>}<small>{authority?.department||"Department being identified"}{authority?.jurisdiction ? ` · ${authority.jurisdiction}` : ""}</small></b></div><div className="contact-actions"><small className={hasVerifiedEmail?"verified-contact":"fallback-contact"}>{hasVerifiedEmail?<><ShieldCheck size={13}/> {liveOffice ? "AI-found official contact" : "Verified directory contact"}</>:<>Official email unavailable</>}</small>{officeError && <small className="lookup-note">Live office lookup unavailable; showing the verified directory fallback.</small>}<div className="contact-line"><Phone size={15}/><span>{authority?.phone_number||authority?.phone||authority?.helpline||"Contact number unavailable"}</span></div><div className="contact-line"><Mail size={15}/><span>{authority?.official_email||"Email unavailable"}</span></div></div><div className="timeline"><h3>Tracking history</h3>{history.map((h,n)=><div className="timeline-item" key={n}><i className={n===history.length-1?"current":""}/><div><b>{statusLabels[h.new_status]||h.new_status}</b><small>{new Date(h.created_at).toLocaleString()} · {h.note||"Status updated"}</small></div></div>)}</div>{canUpdateStatus&&<div className="admin-update"><select value={status} onChange={e=>setStatus(e.target.value)}>{Object.entries(statusLabels).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select><button className="primary compact" onClick={update}>Update status</button></div>}</aside></div>
}
function LocationPicker({onPick}) {
  useMapEvents({ click: event => onPick([event.latlng.lat, event.latlng.lng], "map") });
  return null;
}

function ReportModal({onClose,onDone,onError}) {
  const [description,setDescription]=useState(""),[category,setCategory]=useState("roads"),[files,setFiles]=useState([]),[busy,setBusy]=useState(false);
  const [location,setLocation]=useState([25.6093,85.1376]),[locationSource,setLocationSource]=useState("demo"),[locating,setLocating]=useState(false);
  const chooseDeviceLocation=()=>{
    if (!navigator.geolocation) { onError("This browser does not support device location. Choose a point on the map."); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      position=>{ setLocation([position.coords.latitude,position.coords.longitude]); setLocationSource("device"); setLocating(false); },
      error=>{ setLocating(false); onError(error.code===1 ? "Location permission was denied. Choose a point on the map instead." : "Device location could not be fetched. Choose a point on the map instead."); },
      { enableHighAccuracy:true, timeout:10000, maximumAge:0 }
    );
  };
  const submit=async e=>{
    e.preventDefault();
    if(!files.length){onError("Please attach a photograph of the issue.");return}
    if(!location){onError("Choose a location on the map or use device location.");return}
    setBusy(true);
    const form=new FormData();
    form.append("description",description);form.append("category",category);
    form.append("latitude",String(location[0]));form.append("longitude",String(location[1]));
    form.append("location_text",locationSource==="device"?"Device location":"Map-selected location");
    files.forEach(f=>form.append("files",f));
    try{const report=await request("/issues",{method:"POST",body:form});onDone(report)}catch(err){onError(err.message)}finally{setBusy(false)}
  };
  return <div className="modal-backdrop"><form className="modal report-modal" onSubmit={submit}>
    <button type="button" className="close" onClick={onClose}><X size={19}/></button><span className="eyebrow accent">NEW FIELD REPORT</span><h2>What needs attention?</h2>
    <p className="muted">Describe the problem, then choose the exact location or use your device GPS.</p>
    <label>Issue category<select value={category} onChange={e=>setCategory(e.target.value)}>{Object.entries(labels).map(([v,l])=><option value={v} key={v}>{l}</option>)}</select></label>
    <label>Description<textarea required maxLength="2000" rows="4" placeholder="Describe what you noticed..." value={description} onChange={e=>setDescription(e.target.value)}/></label>
    <label className="upload"><Upload size={20}/><span>{files.length?`${files.length} photo${files.length>1?"s":""} selected`:"Upload photographic evidence"}<small>JPG, PNG or WEBP · max 10 MB each</small></span><input type="file" accept="image/jpeg,image/png,image/webp" multiple required onChange={e=>setFiles([...e.target.files])}/></label>
    <div className="location-actions"><button type="button" className="secondary" onClick={chooseDeviceLocation} disabled={locating}><MapPin size={16}/>{locating?"Fetching device location...":"Use device location"}</button><span>or click the map</span></div>
    <div className="location-picker"><MapContainer center={location} zoom={13} scrollWheelZoom className="picker-map"><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/><LocationPicker onPick={(point,source)=>{setLocation(point);setLocationSource(source)}}/><CircleMarker center={location} radius={9} pathOptions={{color:"#fff",weight:2,fillColor:"#287d72",fillOpacity:1}}/></MapContainer></div>
    <div className="location-confirm"><MapPin size={17}/><span><b>{locationSource==="device"?"Device location fetched":"Location selected on map"}</b><small>{location[0].toFixed(5)}, {location[1].toFixed(5)}</small></span><CheckCircle2 size={17}/></div>
    <button disabled={busy||locating} className="primary submit">{busy?"Saving report...":"Submit civic report"} <ChevronRight size={17}/></button><small className="privacy"><ShieldCheck size={13}/> Your contact details are not shared in this demo.</small>
  </form></div>
}
createRoot(document.getElementById("root")).render(<App />);
