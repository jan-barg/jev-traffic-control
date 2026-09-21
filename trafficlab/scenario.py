"""A schematic 12-intersection network with observed, balanced AM turn volumes.

Geometry, lanes, signal plans, vehicle mix and stochastic arrivals are assumptions.
The figure's internal counts determine turn probabilities, not forced internal flows.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import random
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import sumolib

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenario"
COUNTS = json.loads((ROOT / "data/midtown_am.json").read_text())
SPEED = 11.176  # 25 mph, an assumed desired speed cap.


def topology(buffer=180.0, avenue_lanes=3):
    nodes, edges, junctions = {}, {}, {}
    for ave in (7, 6):
        x = 0.0 if ave == 7 else 260.0
        for st in range(25, 31):
            ident = f"{ave}_{st}"
            nodes[ident] = (x, (st - 25) * 80.0, "traffic_light")
        start, finish = (31, 24) if ave == 7 else (24, 31)
        nodes[f"{ave}_{start}"] = (x, 400 + buffer if start == 31 else -buffer, "priority")
        nodes[f"{ave}_{finish}"] = (x, 400 + buffer if finish == 31 else -buffer, "priority")
        order = list(range(31, 23, -1)) if ave == 7 else list(range(24, 32))
        for a, b in zip(order, order[1:]):
            eid = f"a{ave}_{a}_{b}"
            edges[eid] = {"from":f"{ave}_{a}", "to":f"{ave}_{b}", "lanes":avenue_lanes, "kind":"avenue"}
    for st in range(25,31):
        nodes[f"W{st}"] = (-buffer, (st-25)*80.0, "priority")
        nodes[f"E{st}"] = (260+buffer, (st-25)*80.0, "priority")
        order = [f"W{st}",f"7_{st}",f"6_{st}",f"E{st}"]
        if st % 2:
            order.reverse()
        for a,b in zip(order,order[1:]):
            edges[f"s{st}_{a}_{b}"] = {"from":a, "to":b, "lanes":1, "kind":"cross"}
    for ident, counts in COUNTS["counts"].items():
        incoming = {e["kind"]:eid for eid,e in edges.items() if e["to"]==ident}
        outgoing = {e["kind"]:eid for eid,e in edges.items() if e["from"]==ident}
        junctions[ident] = {"incoming":incoming,"outgoing":outgoing,"counts":counts}
    return nodes,edges,junctions


def validate_flow_balance():
    _,edges,js = topology()
    errors=[]
    for eid,e in edges.items():
        if e["from"] not in js or e["to"] not in js:
            continue
        src,dst = js[e["from"]]["counts"], js[e["to"]]["counts"]
        out = src[0]+src[3] if e["kind"]=="avenue" else src[2]+src[1]
        inc = dst[0]+dst[1] if e["kind"]=="avenue" else dst[2]+dst[3]
        if out!=inc:
            errors.append({"edge":eid,"out":out,"in":inc})
    if errors:
        raise ValueError(f"Counts do not balance: {errors}")
    return {"internal_edges_checked":sum(e['from'] in js and e['to'] in js for e in edges.values()),"errors":errors}


def build_network(directory=SCENARIO, buffer=180, avenue_lanes=3, avenue_green=52, progression_speed=9):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    nodes,edges,js=topology(buffer,avenue_lanes)
    nr=ET.Element("nodes")
    for ident,(x,y,kind) in nodes.items():
        ET.SubElement(nr,"node",id=ident,x=str(x),y=str(y),type=kind)
    er=ET.Element("edges")
    for ident,e in edges.items():
        ET.SubElement(er,"edge",id=ident,**{"from":e['from'],"to":e['to'],"numLanes":str(e['lanes']),"speed":str(SPEED),"priority":"2" if e['kind']=='avenue' else '1'})
    ET.ElementTree(nr).write(directory/'network.nod.xml')
    ET.ElementTree(er).write(directory/'network.edg.xml')
    subprocess.run([sumolib.checkBinary('netconvert'),'-n',str(directory/'network.nod.xml'),'-e',str(directory/'network.edg.xml'),'-o',str(directory/'network.net.xml'),'--no-turnarounds','true','--junctions.corner-detail','5','--tls.default-type','static','--no-warnings','true'],check=True,capture_output=True,text=True)
    net=ET.parse(directory/'network.net.xml')
    # Replace generated programs with two non-conflicting approaches and clearance.
    for tl in net.findall('tlLogic'):
        ident=tl.get('id'); links=[c for c in net.findall('connection') if c.get('tl')==ident]
        size=1+max(int(c.get('linkIndex')) for c in links)
        avenue={int(c.get('linkIndex')) for c in links if c.get('from')==js[ident]['incoming']['avenue']}
        state_a=''.join('G' if k in avenue else 'r' for k in range(size))
        state_c=''.join('r' if k in avenue else 'G' for k in range(size))
        for p in list(tl): tl.remove(p)
        # Coordinate avenues at a nominal 9 m/s progression. Not an actual DOT plan.
        ave,st=map(int,ident.split('_')); order=(30-st) if ave==7 else (st-25)
        tl.set('offset',str((-order*80/progression_speed)%90 if progression_speed else 0))
        for duration,state,name in [(avenue_green,state_a,'avenue'),(3,state_a.replace('G','y'),'yellow_avenue'),(1,'r'*size,'all_red'),(82-avenue_green,state_c,'cross'),(3,state_c.replace('G','y'),'yellow_cross'),(1,'r'*size,'all_red')]:
            ET.SubElement(tl,'phase',duration=str(duration),state=state,name=name)
        js[ident]['states']={'avenue':state_a,'cross':state_c}
    net.write(directory/'network.net.xml',encoding='utf-8',xml_declaration=True)
    snet=sumolib.net.readNet(str(directory/'network.net.xml'),withInternal=True)
    visual={"nodes":[{"id":n.get('id'),"x":float(n.get('x')),"y":float(n.get('y')),"controlled":n.get('id') in js} for n in net.findall('junction') if not n.get('id').startswith(':')],"edges":[]}
    for eid,e in edges.items():
        se=snet.getEdge(eid)
        visual['edges'].append({"id":eid,**e,"shape":[list(p) for p in se.getShape()],"lane_shapes":[[list(p) for p in l.getShape()] for l in se.getLanes()],"length":se.getLength()})
    metadata={"id":"midtown_south_am","junctions":js,"edges":edges,"visual":visual,"balance":validate_flow_balance(),"buffer_m":buffer,"avenue_lanes":avenue_lanes,"avenue_green_s":avenue_green,"progression_speed_mps":progression_speed,"geometry":"Schematic NYC grid; 80 m blocks, 260 m avenues; not surveyed geometry","signal_plan":f"Assumed 90 s coordinated plan: {avenue_green}/{82-avenue_green} s greens, 3 s yellow, 1 s all-red","pedestrians":"Not explicitly simulated; all smart greens have a 22 s minimum. No pedestrian-benefit claim."}
    (directory/'network.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return metadata


def build_demand(seed, scenario='am', warmup=180, duration=600, directory=SCENARIO, multiplier=1.0):
    directory=Path(directory); meta=json.loads((directory/'network.json').read_text())
    edges,js=meta['edges'],meta['junctions']; rng=random.Random(seed)
    arrivals=[]; end=warmup+duration
    for eid,e in sorted(edges.items()):
        if e['from'] in js: continue
        c=js[e['to']]['counts']; rate=(c[0]+c[1] if e['kind']=='avenue' else c[2]+c[3])*multiplier
        t=0.0
        while True:
            # Thinning preserves the same random schedule across controller arms.
            t+=rng.expovariate(rate*1.5/3600)
            if t>=end: break
            factor=1.0
            if scenario=='surge' and warmup+duration*.25<=t<warmup+duration*.75: factor=1.5
            if rng.random()>factor/1.5: continue
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


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--buffer',type=float,default=180); parser.add_argument('--avenue-lanes',type=int,default=3); parser.add_argument('--directory',type=Path,default=SCENARIO)
    args=parser.parse_args(); meta=build_network(args.directory,args.buffer,args.avenue_lanes)
    print(json.dumps({'signals':len(meta['junctions']),'balance':meta['balance'],'directory':str(args.directory)}))
