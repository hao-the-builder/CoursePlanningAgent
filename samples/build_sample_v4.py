from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation

F="Arial"
H_FILL=PatternFill("solid",start_color="1F3864"); TERM_F=PatternFill("solid",start_color="BDD7EE"); SUBT=PatternFill("solid",start_color="F2F2F2")
EX_HDR=PatternFill("solid",start_color="F8CBAD"); EX_ROW=PatternFill("solid",start_color="FCE4D6")
TOT=PatternFill("solid",start_color="1F3864"); SEC=PatternFill("solid",start_color="D9E1F2")
BAN=PatternFill("solid",start_color="FFF2CC"); OK=PatternFill("solid",start_color="C6EFCE"); NO=PatternFill("solid",start_color="FFC7CE"); WARN=PatternFill("solid",start_color="FFEB9C")
CC_F=PatternFill("solid",start_color="E2EFDA"); MJ_F=PatternFill("solid",start_color="DDEBF7"); MN_F=PatternFill("solid",start_color="FFF2CC")
TR_F=PatternFill("solid",start_color="EDEDED")
thin=Side(style="thin",color="BFBFBF"); BOX=Border(left=thin,right=thin,top=thin,bottom=thin)
N=Font(name=F); B=Font(name=F,bold=True); BLUE=Font(name=F,color="0000FF"); HDR=Font(name=F,bold=True,color="FFFFFF")
BANNER="SAMPLE — BEng Computer Science + Minor in Mathematics, 2026-27 intake. Courses, transfer/exchange mappings, credits and requirement numbers are illustrative, not verified."
SETTINGS="Plan settings:  Programme = 4 years  ·  Workload = Front-loaded  ·  Exchange = Y3 Spring  ·  Keep free = Y4 Spring  ·  Transfer = 24 credits (IB)  ·  Target load = 15–18"
NC=9

def banner(ws,cols):
    ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=cols)
    c=ws.cell(1,1,BANNER); c.font=Font(name=F,bold=True,color="9C5700"); c.fill=BAN
    c.alignment=Alignment(wrap_text=True,vertical="center"); ws.row_dimensions[1].height=30
    ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=cols)
    ws.cell(2,1,SETTINGS).font=Font(name=F,italic=True,color="404040")
def hdr(ws,r,names):
    for i,n in enumerate(names,1):
        c=ws.cell(r,i,n); c.font=HDR; c.fill=H_FILL; c.border=BOX
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)

def c_(code,name,cr,st,cc="",mj="",mn="",note=""): return (code,name,cr,st,cc,mj,mn,note)
# (semester key, header title, kind, courses)
TERMS=[
("Transfer","BEFORE HKUST · TRANSFER CREDITS (IB advanced standing)","transfer",[
  c_("MATH 1013","Calculus IB (IB Math AA HL)",3,"Transfer",mj="Fundamentals"),
  c_("MATH 1014","Calculus II (IB Math AA HL)",3,"Transfer",mj="Fundamentals",mn="Required"),
  c_("PHYS 1112","General Physics I (IB Physics HL)",3,"Transfer",mj="Fundamentals"),
  c_("PHYS 1114","General Physics II (IB Physics HL)",3,"Transfer"),
  c_("CHEM 1004","Chemistry (IB)",3,"Transfer"),
  c_("ECON 2103","Principles of Microeconomics (IB Economics)",3,"Transfer"),
  c_("Unspecified","Unspecified transfer credit (IB)",6,"Transfer",note="Confirm with Academic Registry how this counts")]),
("Y1 Fall","YEAR 1 · FALL 2026 (current term)","regular",[
  c_("COMP 1023","Intro to Computational Problem Solving (Python)",3,"Current",mj="Fundamentals"),
  c_("MATH 2111","Matrix Algebra",3,"Current",mj="Fundamentals",mn="Required",note="Double-counts Major + Minor"),
  c_("LANG 1407","English Communication for Engineering",3,"Current",cc="E-Comm"),
  c_("LANG 1416","Chinese Communication",3,"Current",cc="C-Comm"),
  c_("AISC 1000","Foundations of AI Literacy: Human-AI Orchestration",3,"Current",cc="HAIC"),
  c_("COMP 4900","Academic & Professional Development",0,"Current",mj="Core",note="0 credits; every term in residence")]),
("Y1 Spring","YEAR 1 · SPRING 2027","regular",[
  c_("COMP 2012H","Honors OOP and Data Structures",5,"Planned",mj="Core"),
  c_("COMP 2711","Discrete Mathematical Tools for CS",3,"Planned",mj="Core"),
  c_("MATH 2411","Applied Statistics",3,"Planned",mj="Fundamentals",mn="Elective",note="Double-counts Major + Minor"),
  c_("HMAW 1905","Habits, Mindsets, and Wellness",3,"Planned",cc="HMW"),
  c_("CC — Arts","Common Core Arts course (you choose)",3,"Planned",cc="Arts",note="Slot: options in the document"),
  c_("COMP 4900","Academic & Professional Development",0,"Planned",mj="Core")]),
("Y2 Fall","YEAR 2 · FALL 2027","regular",[
  c_("COMP 2611","Computer Organization",3,"Planned",mj="Core"),
  c_("COMP 3711","Design and Analysis of Algorithms",3,"Planned",mj="Core"),
  c_("COMP 3311","Database Management Systems",3,"Planned",mj="Core"),
  c_("MATH 2421","Probability",3,"Planned",mn="Elective"),
  c_("CC — Science","Common Core Science course (you choose)",3,"Planned",cc="Science",note="Slot: options in the document"),
  c_("CC — Social Analysis","Common Core Social Analysis course (you choose)",3,"Planned",cc="Social Analysis",note="Slot: options in the document"),
  c_("COMP 4900","Academic & Professional Development",0,"Planned",mj="Core")]),
("Y2 Spring","YEAR 2 · SPRING 2028","regular",[
  c_("COMP 3111","Software Engineering",3,"Planned",mj="Core"),
  c_("COMP 3511","Operating Systems",3,"Planned",mj="Core"),
  c_("COMP 4211","Machine Learning",3,"Planned",mj="Depth Elective (AI)"),
  c_("MATH 3423","Statistical Inference",3,"Planned",mn="Elective"),
  c_("CC — Any area","Common Core course, any area (you choose)",3,"Planned",cc="Other areas",note="Slot: options in the document"),
  c_("CC — Any area","Common Core course, any area (you choose)",3,"Planned",cc="Other areas",note="Slot: options in the document"),
  c_("COMP 4900","Academic & Professional Development",0,"Planned",mj="Core")]),
("Y3 Fall","YEAR 3 · FALL 2028","regular",[
  c_("COMP 4221","Natural Language Processing",3,"Planned",mj="Depth Elective (AI)"),
  c_("COMP 4471","Deep Learning in Computer Vision",3,"Planned",mj="Depth Elective (AI)"),
  c_("COMP 4421","Image Processing",3,"Planned",mj="Depth Elective (AI)"),
  c_("Free elective","Free elective (you choose)",3,"Planned",note="Slot: options in the document"),
  c_("COMP 4900","Academic & Professional Development",0,"Planned",mj="Core")]),
("Y3 Spring","YEAR 3 · SPRING 2029 · ✈️ EXCHANGE (host university TBD)","exchange",[
  c_("Host course","Machine Learning Systems  ≈ COMP depth elective",3,"Exchange",mj="Depth Elective (AI)",note="Pending department approval of mapping"),
  c_("Host course","Introduction to Philosophy  ≈ CC Humanities",3,"Exchange",cc="Humanities",note="Pending CC approval of mapping"),
  c_("Host course","Numerical Analysis  ≈ MATH elective",3,"Exchange",mn="Elective",note="Pending MATH dept approval"),
  c_("Host course","Local language course",3,"Exchange",note="Free elective; pending credit transfer"),
  c_("Host course","Technology Entrepreneurship",3,"Exchange",note="Free elective; pending credit transfer")]),
("Y3 Summer","YEAR 3 · SUMMER 2029","summer",[
  c_("COMP 1991","Industrial Experience (summer internship)",0,"Planned",mj="Final Year Project")]),
("Y4 Fall","YEAR 4 · FALL 2029","regular",[
  c_("COMP 4981","Final Year Project",6,"Planned",mj="Final Year Project"),
  c_("COMP 4900","Academic & Professional Development",0,"Planned",mj="Core")]),
("Y4 Spring","YEAR 4 · SPRING 2030","free",[]),
]

wb=Workbook(); ws=wb.active; ws.title="Course Plan"
banner(ws,NC)
hdr(ws,3,["Semester","Course Code","Course Name","Credits","Status","Common Core","Major Requirements","Minor Requirements","Notes"])
r=4; sub_rows=[]; first=4
for key,title,kind,courses in TERMS:
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=NC)
    c=ws.cell(r,1,title); c.font=B; c.fill=EX_HDR if kind=="exchange" else TERM_F
    r+=1; s=r
    if not courses:
        ws.cell(r,1,key).font=N; ws.cell(r,3,"No courses — free term").font=Font(name=F,italic=True)
        for i in range(1,NC+1): ws.cell(r,i).border=BOX
        r+=1
    for code,name,cr,st,cc,mj,mn,note in courses:
        for i,v in enumerate([key,code,name,cr,st,cc,mj,mn,note],1):
            x=ws.cell(r,i,v if v!="" else None); x.font=N; x.border=BOX
        ws.cell(r,4).alignment=Alignment(horizontal="center")
        if kind=="transfer":
            for i in range(1,6): ws.cell(r,i).fill=TR_F
        if kind=="exchange":
            for i in range(1,6): ws.cell(r,i).fill=EX_ROW
        if cc: ws.cell(r,6).fill=CC_F
        if mj: ws.cell(r,7).fill=MJ_F
        if mn: ws.cell(r,8).fill=MN_F
        r+=1
    e=r-1
    ws.cell(r,3,f"{key} total").font=B
    ws.cell(r,4,f"=SUM(D{s}:D{e})").font=B; ws.cell(r,4).alignment=Alignment(horizontal="center")
    for col in "FGH":
        ws[f"{col}{r}"]=f'=SUMPRODUCT(D{s}:D{e},--({col}{s}:{col}{e}<>""))'
        ws[f"{col}{r}"].font=B; ws[f"{col}{r}"].number_format='0" cr"'
    if kind=="transfer": tag='"Earned before HKUST"'
    elif kind=="exchange": tag='"✈️ Exchange: credits pending approval"'
    elif kind=="summer": tag=f'IF(D{r}=0,"Internship / no credit-bearing courses","Summer term")'
    else: tag=f'IF(D{r}=0,"🟢 Free term",IF(D{r}>=18,"🔴 Heavy",IF(D{r}<12,"🟡 Light — check minimum load","Normal")))'
    ws.cell(r,9,"="+tag).font=B
    for i in range(1,NC+1): ws.cell(r,i).fill=SUBT; ws.cell(r,i).border=BOX
    sub_rows.append(r); r+=1
last=r-1
r+=1
# ---- programme total line ----
refs=lambda col: "="+"+".join(f"{col}{x}" for x in sub_rows)
ws.cell(r,1,"PROGRAMME TOTAL").font=HDR
ws.cell(r,3,"4-year plan · Fall 2026 → Spring 2030 · graduation needs 120").font=HDR
ws.cell(r,4,refs("D")).font=HDR
for col in "FGH": ws[f"{col}{r}"]=refs(col); ws[f"{col}{r}"].font=HDR; ws[f"{col}{r}"].number_format='0" cr"'
ws.cell(r,5,f'=IF(D{r}>=120,"✅ ≥120","❌ <120")').font=HDR
tr,ex=sub_rows[0],sub_rows[6]
ws.cell(r,9,f'="Transfer "&D{tr}&" · Exchange "&D{ex}&" · HKUST "&(D{r}-D{tr}-D{ex})').font=HDR
for i in range(1,NC+1): ws.cell(r,i).fill=TOT; ws.cell(r,i).border=BOX
ws.cell(r,4).alignment=Alignment(horizontal="center")
tot_line=r; r+=2
ws.cell(r,1,"Legend").font=B; r+=1
for t in ["Grey rows = transfer credits · Orange = exchange term (credits count only after approval) · Blue band = term header · Grey band = term total.",
          "Term total row: Credits = all credits that term; Common Core / Major / Minor columns = credits counting toward each (a course can count toward two).",
          "Rows with no Common Core / Major / Minor entry are free electives. '(you choose)' rows are slots; the agent suggests options in the document.",
          "Status: Taken / Current / Transfer = done · Planned = future · Exchange = future, pending credit transfer approval."]:
    ws.cell(r,1,t).font=N; r+=1
dv=DataValidation(type="list",formula1='"Taken,Current,Transfer,Planned,Exchange"'); ws.add_data_validation(dv); dv.add(f"E4:E{last}")
for col,w in zip("ABCDEFGHI",[11,16,50,9,11,16,22,19,40]): ws.column_dimensions[col].width=w
ws.freeze_panes="A4"

# ---------------- Progress ----------------
p=wb.create_sheet("Progress"); banner(p,7)
hdr(p,3,["Requirement","Required","Done","Planned","Exchange (pending)","Remaining","Status"])
PL="'Course Plan'"; rg=lambda c: f"{PL}!${c}$4:${c}${last}"
DONE=("Taken","Current","Transfer")
sumst=lambda col,key,sts: "+".join(f'SUMIFS({rg("D")},{rg(col)},"{key}",{rg("E")},"{s}")' for s in sts)
st_f=lambda r: f'=IF(C{r}+D{r}>=B{r},"✅ On track",IF(C{r}+D{r}+E{r}>=B{r},"⚠️ Needs exchange approval","❌ Short"))'
r=4
def secrow(title):
    global r
    p.cell(r,1,title).font=B
    for i in range(1,8): p.cell(r,i).fill=SEC; p.cell(r,i).border=BOX
    r+=1
def section(title,col,items):
    global r
    secrow(title); s=r
    for label,key,req in items:
        p.cell(r,1,"   "+label).font=N; p.cell(r,2,req).font=BLUE
        p.cell(r,3,"="+sumst(col,key,DONE)).font=N
        p.cell(r,4,"="+sumst(col,key,["Planned"])).font=N
        p.cell(r,5,"="+sumst(col,key,["Exchange"])).font=N
        p.cell(r,6,f"=MAX(0,B{r}-C{r}-D{r}-E{r})").font=N; p.cell(r,7,st_f(r)).font=N
        for i in range(1,8): p.cell(r,i).border=BOX
        r+=1
    p.cell(r,1,"   Subtotal").font=B
    for i,cl in zip(range(2,7),"BCDEF"): p.cell(r,i,f"=SUM({cl}{s}:{cl}{r-1})").font=B
    p.cell(r,7,st_f(r)).font=B
    for i in range(1,8): p.cell(r,i).border=BOX
    r+=2
section("MAJOR REQUIREMENTS — BEng Computer Science","G",[
 ("Fundamentals (maths, physics, intro programming)","Fundamentals",18),("Core courses","Core",23),
 ("Depth electives (AI)","Depth Elective (AI)",15),("Final Year Project + Industrial Experience","Final Year Project",6)])
section("COMMON CORE — 30-credit program","F",[
 ("HAIC — Human-AI Co-Creation","HAIC",3),("HMW — Habits, Mindsets, Wellness","HMW",3),
 ("English Communication","E-Comm",3),("Chinese Communication","C-Comm",3),("Arts","Arts",3),
 ("Humanities","Humanities",3),("Science","Science",3),("Social Analysis","Social Analysis",3),("Other areas","Other areas",6)])
section("MINOR REQUIREMENTS — Minor in Mathematics","H",[("Required courses","Required",6),("Electives","Elective",12)])

secrow("GRADUATION — 120 credits")
allst=lambda sts: "="+"+".join(f'SUMIFS({rg("D")},{rg("E")},"{s}")' for s in sts)
p.cell(r,1,"   Total credits (each course counted once)").font=B
p.cell(r,2,120).font=Font(name=F,bold=True,color="0000FF")
p.cell(r,3,allst(DONE)).font=B; p.cell(r,4,allst(["Planned"])).font=B; p.cell(r,5,allst(["Exchange"])).font=B
p.cell(r,6,f"=MAX(0,B{r}-C{r}-D{r}-E{r})").font=B; p.cell(r,7,st_f(r)).font=B
for i in range(1,8): p.cell(r,i).border=BOX
gr=r; r+=1
def isdone(): return "(("+")+(".join(f'{rg("E")}="{s}"' for s in DONE)+"))"
free=lambda cond: f'=SUMPRODUCT({rg("D")},--({rg("F")}=""),--({rg("G")}=""),--({rg("H")}=""),{cond})'
dbl=lambda cond: f'=SUMPRODUCT({rg("D")},--({rg("G")}<>""),--({rg("H")}<>""),{cond})'
for lab,c3,c4,c5 in [
  ("   …of which transfer credits",allst(["Transfer"]),None,None),
  ("   …of which free electives",free(isdone()),free(f'--({rg("E")}="Planned")'),free(f'--({rg("E")}="Exchange")')),
  ("   Credits double-counted Major + Minor",dbl(isdone()),dbl(f'--({rg("E")}="Planned")'),dbl(f'--({rg("E")}="Exchange")'))]:
    p.cell(r,1,lab).font=N; p.cell(r,3,c3).font=N
    if c4: p.cell(r,4,c4).font=N
    if c5: p.cell(r,5,c5).font=N
    for i in range(1,8): p.cell(r,i).border=BOX
    r+=1
r+=1
secrow("THINGS TO CHECK (validator warnings)")
for t in ["✈️ Exchange (Y3 Spring): 15 credits count only after approval. Depth electives, Humanities and Minor electives depend on it — get course mappings pre-approved before you go.",
          "✈️ COMP 4900 is not taken in the exchange term (not in residence at HKUST).",
          "⚠️ Y4 Fall has only 6 credits: check HKUST's minimum credit load per regular term, or whether you could graduate after Y4 Fall.",
          "⚠️ Final Year Project: confirm whether COMP 4981 must run across two terms.",
          "⚠️ 6 credits of transfer are 'unspecified': confirm with the Academic Registry how they count.",
          "⚠️ Y2 Fall and Y2 Spring are 18 credits: heavy if you're aiming for a high GPA.",
          "ℹ️ Done = Taken + Current + Transfer. Blue numbers are requirement inputs; everything else is a formula over Course Plan.",
          "ℹ️ Data tier: auto-extracted (sample). Verify with your academic advisor before relying on this plan."]:
    p.cell(r,1,t).font=N; r+=1
p.conditional_formatting.add(f"G4:G{gr}",FormulaRule(formula=['LEFT($G4,1)="✅"'],fill=OK))
p.conditional_formatting.add(f"G4:G{gr}",FormulaRule(formula=['LEFT($G4,1)="❌"'],fill=NO))
p.conditional_formatting.add(f"G4:G{gr}",FormulaRule(formula=['LEFT($G4,1)="⚠"'],fill=WARN))
for col,w in zip("ABCDEFG",[48,10,9,9,12,11,26]): p.column_dimensions[col].width=w
p.freeze_panes="A4"
wb.save("/home/claude/samples/sample_course_plan_v4.xlsx")
