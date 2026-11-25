import { activeCompanyHeaders } from "./company";

const rawBase = import.meta.env.VITE_API_BASE_URL;
const BASE_URL = rawBase ? rawBase.replace(/\/+$/, "") : null;

const request = async (path, options = {}, token) => {
  const cleanPath = path.replace(/^\/+/, "");
  const url = BASE_URL
    ? BASE_URL.endsWith("/api")
      ? `${BASE_URL}/${cleanPath}`
      : `${BASE_URL}/api/${cleanPath}`
    : `/api${path}`;
  const { headers, ...requestOptions } = options;
  const response = await fetch(url, {
    ...requestOptions,
    headers: {
      "Content-Type": "application/json",
      ...activeCompanyHeaders(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers || {}),
    },
  });
  const data = await response.json().catch(()=>({}));
  if(!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
};
export const getMeetings=(token)=>request("/meetings",{},token);
export const getExecutives=(token)=>request("/executives",{},token);
export const getMeetingProgress=(id,afterId,token)=>request(`/meetings/${id}/progress?after_id=${afterId}`,{},token);
export const createMeeting=(body,token)=>request("/meetings",{method:"POST",body:JSON.stringify(body)},token);
export const runMeeting=(id,token)=>request(`/meetings/${id}/run`,{method:"POST"},token);
export const recordDecision=(id,body,token)=>request(`/meetings/${id}/decision`,{method:"POST",body:JSON.stringify(body)},token);
export const getLLMSettings=(token)=>request("/llm/settings",{},token);
export const createLLMSource=(body,token)=>request("/llm/sources",{method:"POST",body:JSON.stringify(body)},token);
export const updateLLMSource=(id,body,token)=>request(`/llm/sources/${id}`,{method:"PATCH",body:JSON.stringify(body)},token);
export const deleteLLMSource=(id,token)=>request(`/llm/sources/${id}`,{method:"DELETE"},token);
export const testLLMSource=(id,token)=>request(`/llm/sources/${id}/test`,{method:"POST"},token);
export const setAgentLLMRoute=(role,body,token)=>request(`/llm/routes/${role}`,{method:"PUT",body:JSON.stringify(body)},token);
export const setAgentLLMRoutesBulk=(body,token)=>request("/llm/routes/bulk",{method:"PUT",body:JSON.stringify(body)},token);
export const clearAgentLLMRoute=(role,token)=>request(`/llm/routes/${role}`,{method:"DELETE"},token);
export const getEvidenceRecords=(token)=>request("/evidence",{},token);
export const createEvidenceRecord=(body,token)=>request("/evidence",{method:"POST",body:JSON.stringify(body)},token);
export const updateEvidenceRecord=(id,body,token)=>request(`/evidence/${id}`,{method:"PATCH",body:JSON.stringify(body)},token);
export const deleteEvidenceRecord=(id,token)=>request(`/evidence/${id}`,{method:"DELETE"},token);
export const getResearchSettings=(token)=>request("/research/settings",{},token);
export const updateTavilyKey=(body,token)=>request("/research/settings/tavily",{method:"PUT",body:JSON.stringify(body)},token);
export const searchResearchSources=(body,token)=>request("/research/search",{method:"POST",body:JSON.stringify(body)},token);
export const getDecisionRecords=(token,params)=>{const query=params?new URLSearchParams(Object.entries(params).filter(([,v])=>v!==undefined&&v!=="")).toString():"";return request(`/decisions${query?`?${query}`:""}`,{},token)};
export const getDueDecisionRecords=(token)=>request("/decisions/due",{},token);
export const createDecisionRecord=(body,token)=>request("/decisions",{method:"POST",body:JSON.stringify(body)},token);
export const updateDecisionRecord=(id,body,token)=>request(`/decisions/${id}`,{method:"PATCH",body:JSON.stringify(body)},token);
export const deleteDecisionRecord=(id,token)=>request(`/decisions/${id}`,{method:"DELETE"},token);
export const getDecisionById=(id,token)=>request("/decisions/"+id,{},token);
export const reviewDecisionRecord=(id,body,token)=>request(`/decisions/${id}/review`,{method:"POST",body:JSON.stringify(body)},token);
export const recallMemory=(query,opts,token)=>{const params=new URLSearchParams({q:query});if(opts?.limit)params.set("limit",String(opts.limit));if(opts?.excludeMeetingId)params.set("exclude_meeting_id",String(opts.excludeMeetingId));return request(`/decisions/memory?${params.toString()}`,{},token)};
export const syncDecisionRecords=(token)=>request("/decisions/sync",{method:"POST"},token);

// Programme 4 — Founder workspace and company context
export const getCompany=(token)=>request("/company",{},token);
export const getCompanies=(token)=>request("/companies",{},token);
export const getCompanyProfile=(id,token)=>request(`/companies/${id}`,{},token);
export const createCompanyProfile=(body,token)=>request("/companies",{method:"POST",body:JSON.stringify(body)},token);
export const updateCompanyProfile=(id,body,token)=>request(`/companies/${id}`,{method:"PATCH",body:JSON.stringify(body)},token);
export const deleteCompanyProfile=(id,force,token)=>request(`/companies/${id}${force?"?force=true":""}`,{method:"DELETE"},token);
export const updateCompany=(body,token)=>request("/company",{method:"PATCH",body:JSON.stringify(body)},token);
export const getCompanyContext=(token)=>request("/company/context",{},token);
export const getGovernance=(token)=>request("/company/governance",{},token);
export const getPerformance=(token)=>request("/performance",{},token);

const companyList = (path) => ({
  create: (body,token)=>request(`/company/${path}`,{method:"POST",body:JSON.stringify(body)},token),
  update: (id,body,token)=>request(`/company/${path}/${id}`,{method:"PATCH",body:JSON.stringify(body)},token),
  remove: (id,token)=>request(`/company/${path}/${id}`,{method:"DELETE"},token),
});
export const companyPriorities = companyList("priorities");
export const companyConstraints = companyList("constraints");
export const companyFinancialAssumptions = companyList("financial-assumptions");
export const companyKnowledge = companyList("knowledge");

// Programme 5 — Executive scorecard and founder feedback
export const getPerformanceContributions=(token,params)=>{const query=params?new URLSearchParams(Object.entries(params).filter(([,v])=>v!==undefined&&v!=="")).toString():"";return request(`/performance/contributions${query?`?${query}`:""}`,{},token)};
export const submitExecutiveFeedback=(body,token)=>request("/performance/feedback",{method:"POST",body:JSON.stringify(body)},token);
export const deleteExecutiveFeedback=(id,token)=>request(`/performance/feedback/${id}`,{method:"DELETE"},token);

// Programme 6 — Controlled operational capabilities
export const getOperationsCapabilities=(token)=>request("/operations/capabilities",{},token);
export const getOperationalArtifacts=(token)=>request("/operations/artifacts",{},token);
export const createOperationalArtifact=(body,token)=>request("/operations/artifacts",{method:"POST",body:JSON.stringify(body)},token);
export const regenerateOperationalArtifact=(id,token)=>request(`/operations/artifacts/${id}/regenerate`,{method:"POST"},token);
export const submitOperationalArtifact=(id,token)=>request(`/operations/artifacts/${id}/submit`,{method:"POST"},token);
export const approveOperationalArtifact=(id,body,token)=>request(`/operations/artifacts/${id}/approve`,{method:"POST",body:JSON.stringify(body||{})},token);
export const rejectOperationalArtifact=(id,body,token)=>request(`/operations/artifacts/${id}/reject`,{method:"POST",body:JSON.stringify(body||{})},token);
export const deleteOperationalArtifact=(id,token)=>request(`/operations/artifacts/${id}`,{method:"DELETE"},token);

