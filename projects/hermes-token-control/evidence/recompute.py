import json, statistics, math
from pathlib import Path
calls=[2,12,6,11,11,16,10,2,6,2,25,24,6,1,8,72,15,5,5,9,5,16,11,18,9,7,26,8,24,19,7,15,17,7,24,19,2,26,5,27,5,12,3,5,5,2,11,3,3,3,3,9,3,5,44,7,10,11,21,4,15,1,39,10,7,10,11,5,14,18,9,21,9,5,24,45,3,38,2,12,18,4,10,46,11]
base=443.90
scenarios={}
for name,mratio,mctx,pratio,pctx,aux in [('conservative',.9,48000,.8,16000,5),('target',.6,40000,.25,12000,5),('stress',1,64000,1,24000,5)]:
 m=1357*mratio*mctx/1e6+1.56
 p=1137*pratio*pctx/1e6+1.02
 total=m+p+2.98+aux
 scenarios[name]={'main_M':m,'inbox_M':p,'other_M':2.98,'auxiliary_reserve_M':aux,'total_M':total,'retained_ratio':total/base,'reduction_pct':100*(1-total/base),'factor':base/total}
data={'baseline_M':base,'total_input_M':441.23,'main_input_mean':357.7e6/1357,'largest_session_input_mean':356.49e6/1324,'cron_input_mean':80.64e6/1137,'cron_calls_mean':1137/47,'per_turn':{'n':len(calls),'sum':sum(calls),'mean':statistics.mean(calls),'median':statistics.median(calls),'p95_nearest_rank':sorted(calls)[math.ceil(.95*len(calls))-1],'max':max(calls)},'scenarios':scenarios,'notes':'Rounded input evidence; projections, not production A/B. All original output tokens retained; auxiliary reserve explicitly added. 85 turns not the same population as all API calls.'}
Path(__file__).with_name('projection.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(data,ensure_ascii=False,indent=2))
