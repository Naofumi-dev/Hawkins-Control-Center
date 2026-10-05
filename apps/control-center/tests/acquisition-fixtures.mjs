// Synthetic UI state only. Not imported by production code or packaged in Docker.
export const jobId='70000000-0000-4000-8000-000000000001';
const profileId='70000000-0000-4000-8000-000000000002';
const draftId='70000000-0000-4000-8000-000000000003';
const job={id:jobId,opportunity_id:'70000000-0000-4000-8000-000000000004',title:'Synthetic intake systems role',company:'Example Agency · test data',source_url:'https://www.onlinejobs.ph/jobseekers/job/Synthetic-12345',platform:'onlinejobs',description:'Maintain an intake dashboard and explain your relevant experience. <script>untrusted content must remain text</script>',status:'new',context_version:1,questions:['What relevant work have you completed?'],blockers:[],source_verified_at:'2026-10-05T01:00:00Z',historical_applied_at:null};
const resource={id:profileId,provider:'manual',external_id:'profile',kind:'profile',title:'Reviewed synthetic profile',url:null,version:'v1',content:'Built a fictional intake demo for tests.',verified_at:'2026-10-05T01:00:00Z',active:true};
const savedDraft={id:draftId,kind:'application',revision:1,status:'pending_review',recipient_email:null,subject:'Application for the systems role',body:'I built an intake demo. I can share it for your review.\n\nWhat relevant work have you completed?\nA fictional intake demo.',job_id:jobId,blocker:'application_cutover_required',application_payload:{letter_body:'I built an intake demo. I can share it for your review.',resources:[resource],answers:[{question:job.questions[0],answer:'A fictional intake demo.'}],delivery:'manual',apply_points:1}};
const draftCase=process.env.HAWKINS_TEST_DRAFT_CASE;
let draft=draftCase?null:savedDraft;
const drafting={model_configured:draftCase!=='blocked'};
const letter='I can help your team keep client intake and the next action visible in one place. I built a fictional intake demo covering the same review steps. I can walk you through the relevant parts and see whether they fit your process.';
const qualification={id:'synthetic-eleven',agent:'Eleven',task_type:'qualify_job',context_version:1,opportunity_id:job.opportunity_id,title:'Qualify the systems role',status:draftCase==='blocked'?'blocked':'review',blocker:draftCase==='blocked'?'AI provider is not configured; task retained for manual review':null,result:{summary:'Fits the reviewed demo experience.',evidence:['Maintain an intake dashboard'],missing:[],draft_body:'',suggested_category:''}};
const writing={id:'synthetic-steve',agent:'Steve',task_type:'cover_letter',context_version:1,opportunity_id:job.opportunity_id,title:'Prepare cover letter',status:draftCase==='ready'?'review':'pending',blocker:null,result:draftCase==='ready'?{summary:'A short letter about a clear intake queue.',evidence:['Maintain an intake dashboard'],missing:[],draft_body:letter,suggested_category:'',screening_answers:[{question:job.questions[0],answer:'A fictional intake demo.'}],source_resources:[{id:profileId,version:'v1'}]}:null};
export const acquisitionFixture={ready:true,workflows:[['V0xHCzfFMgKR61yh','Dustin · OnlineJobs','Job discovery'],['hwEDWc0F9Wam1MgB','Eleven + Steve · Score & Draft','Qualification and cover letters'],['x10lpGeWihYhpunW','Hopper · Jobs API','Review and history'],['TaSrrFcWgr0W0Yd7','Client Finder · Discovery','Agency research'],['2PLgsImvFAGw0JTf','Client Finder · Review & Send','Owner approvals'],['VMx5m5ADmApXlkjU','Client Finder · Inbox Monitor','Replies and suppression'],['G2EyMqtsewhrQJAG','Client Finder · Follow-ups','Eligible reminders'],['saO2Ns7Qp604kcvm','Hawkins · Prepare Proposals','Selected calls into proposals']].map(([id,name,purpose])=>({id,name,purpose,active:null,observed_at:null,last_success_at:null})),
 connections:['google','notion','n8n','telegram','onlinejobs','calcom','fathom','ghl','loom'].map(provider=>({provider,identity:null,status:'setup_required',selected:{},verified_at:null,last_success_at:null,error_code:null,enabled:false})),
 jobs:[job],job_total:1,drafting,drafts:draft?[draft]:[],resources:[resource],operations:[],meetings:[],imports:[],recommendations:[{id:'synthetic-task',title:'Review the systems role cover letter',agent:'Hopper',status:'review',reason:'The job source and profile are ready for owner review.',evidence:['Maintain an intake dashboard']}],controls:{applications_enabled:false,application_daily_limit:5,legacy_queue_reconciled_at:null},budget:{used_cents:0,outreach:0,applications:0,replies:0},crm_links:[]};
export function acquisitionResponse(url,method,body={}) {
 if(!url.pathname.startsWith('/api/acquisition'))return null;
 if(method==='GET'){
  if(url.pathname==='/api/acquisition')return acquisitionFixture;
  if(url.pathname==='/api/acquisition/jobs/'+jobId)return {job,draft,drafting,tasks:[qualification,writing],history:[],attempts:[]};
 }
 if(method==='POST'&&url.pathname==='/api/acquisition/application-save'){
  if(body.expected_revision!==(draft?.revision||0))throw new Error('Stale fixture revision');
  if(!draft)draft={...savedDraft,revision:0,application_payload:{...savedDraft.application_payload}};
  draft.subject=body.subject;draft.body=[body.body,...body.answers.map(a=>a.question+'\n'+a.answer)].join('\n\n');draft.application_payload.letter_body=body.body;draft.application_payload.answers=body.answers;draft.revision++;
  acquisitionFixture.drafts=[draft]; return {result:draft};
 }
 if(method==='POST'&&url.pathname==='/api/acquisition/queue'){
  const operation={id:'synthetic-operation',kind:body.kind,status:'pending',error_code:null,created_at:new Date().toISOString()};acquisitionFixture.operations.push(operation);return {result:operation};
 }
 return {error:'Synthetic endpoint has no external side effects'};
}
