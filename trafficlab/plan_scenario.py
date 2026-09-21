"""Additional synthetic demand profiles; original generation remains unchanged."""
import hashlib,json,os,random
import xml.etree.ElementTree as ET
from pathlib import Path
from .scenario import ROOT,SCENARIO,SPEED,build_demand


def demand_factor(scenario,edge,t,warmup,duration):
    kind=edge['kind']
    if scenario=='shift':
        if t<warmup+duration/3:return 1.0
        scenario='dev_cross' if t<warmup+2*duration/3 else 'dev_avenue'
    if scenario=='dev_cross':return .65 if kind=='avenue' else 2.2
    if scenario=='dev_avenue':return 1.4 if kind=='avenue' else .6
    if scenario=='dev_local':return 3.0 if kind=='cross' and edge['to'].endswith(('_26','_28')) else 1.0
    raise ValueError(scenario)


def build_profile_demand(seed, scenario='am', warmup=180, duration=600, directory=SCENARIO, multiplier=1.0):
    if scenario in ('am','surge'): return build_demand(seed,scenario,warmup,duration,directory,multiplier)
    directory=Path(directory); meta=json.loads((directory/'network.json').read_text())
    edges,js=meta['edges'],meta['junctions']; rng=random.Random(seed)
    arrivals=[]; end=warmup+duration
    for eid,e in sorted(edges.items()):
        if e['from'] in js: continue
        c=js[e['to']]['counts']; rate=(c[0]+c[1] if e['kind']=='avenue' else c[2]+c[3])*multiplier
        t=0.0
        while True:
            # Thinning preserves the same random schedule across controller arms.
            t+=rng.expovariate(rate*3.0/3600)
            if t>=end: break
            factor=demand_factor(scenario,e,t,warmup,duration)
            if rng.random()>factor/3.0: continue
            route=[eid]; current=e['to']; kind=e['kind']
            for _ in range(200):
                if current not in js: break
                node=js[current]; through,turn=node['counts'][0:2] if kind=='avenue' else node['counts'][2:4]
                if rng.random()<turn/(through+turn): kind='cross' if kind=='avenue' else 'avenue'
                nxt=node['outgoing'][kind]; route.append(nxt); current=edges[nxt]['to']
            else:
                raise RuntimeError('Route exceeded 200 edges; no silent truncation permitted')
            kind_v='truck' if rng.random()<.05 else 'car'
            arrivals.append({'depart':round(t,3),'route':route,'type':kind_v,'speed_factor':round(rng.uniform(.9,1.05),4),'cohort':t>=warmup})
    arrivals.sort(key=lambda v:v['depart'])
    route_xml=ET.Element('routes')
    for typ,length,accel in [('car',5,2.6),('truck',9,1.3)]:
        ET.SubElement(route_xml,'vType',id=typ,length=str(length),minGap='2.5',accel=str(accel),decel='4.5',sigma='0',tau='1',maxSpeed=str(SPEED),speedDev='0')
    for idx,v in enumerate(arrivals):
        v['id']=f'v{idx}'
        ve=ET.SubElement(route_xml,'vehicle',id=v['id'],depart=str(v['depart']),type=v['type'],departLane='best',departSpeed='max',speedFactor=str(v['speed_factor']))
        ET.SubElement(ve,'route',edges=' '.join(v['route']))
    stem=f'{scenario}_seed{seed}_{warmup}_{duration}_x{multiplier:g}'
    path=directory/'demand'/stem; path.parent.mkdir(exist_ok=True)
    temporary=path.with_suffix(f'.{os.getpid()}.rou.tmp')
    ET.ElementTree(route_xml).write(temporary,encoding='utf-8',xml_declaration=True)
    temporary.replace(path.with_suffix('.rou.xml'))
    payload={'seed':seed,'scenario':scenario,'warmup_s':warmup,'measurement_s':duration,'demand_end_s':end,'multiplier':multiplier,'requested':len(arrivals),'measured_requested':sum(v['cohort'] for v in arrivals),'vehicles':arrivals}
    serialized=json.dumps(payload,sort_keys=True)
    payload['sha256']=hashlib.sha256(serialized.encode()).hexdigest()
    temporary=path.with_suffix(f'.{os.getpid()}.json.tmp')
    temporary.write_text(json.dumps(payload)+'\n')
    temporary.replace(path.with_suffix('.json'))
    return path

