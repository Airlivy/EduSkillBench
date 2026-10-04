"""Build an isolated, reviewable case revision; never overwrite released CSVs.

Content review candidates, not a claim of full independent educational acceptance.
Run from any directory: python3 code/evaluation/revise_cases_20260930.py
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'data/revisions/case-review-20260930'
PATCHES = {}
NOTES = {}
ACCEPTANCE = []


def change(dataset, tid, reason, **fields):
    PATCHES.setdefault((dataset, tid), {}).update(fields)
    NOTES.setdefault((dataset, tid), []).append(reason)


def rubric(*descriptions):
    weights = [40, 30, 20, 10] if len(descriptions) == 4 else [20]*5
    return json.dumps([{'criterion':f'Case-specific criterion {i+1}', 'points':w, 'description':d}
                      for i,(w,d) in enumerate(zip(weights, descriptions))], ensure_ascii=False)


def specific(tid, key, teaching, reject, reason, context=None, prompt=None):
    """Concrete answer anchors plus a contrast case; no fixed surface wording required."""
    expected = ('Answer only the scenario in this case. The following are correctness anchors, '
                'not a mandatory script; accept mathematically or pedagogically equivalent alternatives.\n'
                'Core answer: '+key+'\nClassroom implementation: '+teaching+'\nDo not accept: '+reject)
    fields = {'expected_output': expected,
              'rubric': rubric(
                  'The response is substantively correct for this case. Correctness anchors (equivalent examples are allowed): '+key,
                  'It directly addresses the user\'s requested decision or deliverable, using the stated constraints, '
                  'rather than answering every scenario in the source document. '+teaching,
                  'It explains the reasoning behind the proposed steps and gives a concrete check or feedback action '
                  'appropriate to this case. Do not require classroom outcomes that have not actually been observed.',
                  'It states material assumptions and limitations, avoids invented information, and avoids the following error: '+reject)}
    if context is not None: fields['context']=context
    if prompt is not None: fields['user_prompt']=prompt
    change('cn263',tid,reason,**fields)
    ACCEPTANCE.append({'dataset':'cn263','task_id':tid,'positive_answer_anchor':key+' '+teaching,
                       'negative_answer_example':reject,
                       'acceptance_method':'content review and explicit contrast; no LLM judge run',
                       'independent_subject_review':'pending'})


def read(name):
    with (ROOT/'data'/name).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);return reader.fieldnames,list(reader)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def row_digest(row):
    return digest(json.dumps(row,sort_keys=True,ensure_ascii=False).encode())


FIELDS42, OLD = read('single_turn_tasks.csv')
FIELDS263, NEW = read('single_turn_tasks_cn263.csv')
BYOLD = {r['task_id']:r for r in OLD}
BYNEW = {r['task_id']:r for r in NEW}

# Correct six unambiguous metadata errors; preserve the genuinely graduate task.
for row in OLD:
    if row['education_stage']=='graduate' and ('undergraduate' in row['education_level'].lower()):
        change('original42',row['task_id'],'本科题被标成研究生，影响分学段统计。',education_stage='undergraduate')

# The original flux uses the leading-edge field as the field over the whole loop.
tid='self-explanation-prompt-designer__03'
prompt='''I am creating a first-year university physics module on electromagnetic induction.
Use this corrected worked example to design self-explanation prompts about physical reasoning.
A rectangular conducting loop lies in the plane of the page. Its width w = 0.2 m is along +x,
and its length L = 0.5 m is perpendicular to x in the page. It moves at v = 3 m/s along +x.
For x >= 0, a static magnetic field points into the page with magnitude B(x) = B0*x/d,
where B0 = 0.4 T and d = 1.0 m; for x < 0 the field is zero. The resistance is R = 2 ohms.
At the instant considered the leading edge is at x = 0.3 m, so the loop spans 0.1 to 0.3 m
and is entirely inside the field region. Neglect self-inductance. Take the positive surface
normal into the page, with the associated clockwise positive circuit direction.
Step 1: Phi(x) = L * integral from x-w to x of (B0*u/d) du
= L*B0/d*(w*x - w*w/2) = 0.008 Wb at x = 0.3 m.
Step 2: dPhi/dt = (dPhi/dx)*v, since the field is static and the integration region moves.
Step 3: dPhi/dx = L*B0*w/d = 0.04 Wb/m.
Step 4: signed emf = -0.12 V; its magnitude is 0.12 V.
Step 5: current magnitude = 0.12/2 = 0.06 A.
Step 6: the current is counterclockwise as viewed on the page, opposing the increasing inward flux.
Design self-explanation prompts at the integral, chain-rule, velocity and Lenz-law steps.
For each give its placement, question, a physically deep answer, a shallow restatement and
an appropriate follow-up. Include a quality framework and progressively structured support.
Check the example's assumptions and distinguish signed quantities from magnitudes. Do not
replace the nonuniform field with the leading-edge value over the entire loop.'''
change('original42',tid,'磁通量积分错误，且缺少线圈朝向、磁场方向和符号约定。',user_prompt=prompt,
       expected_output='Physically grounded self-explanation prompts with placement, deep/shallow contrasts, follow-ups and scaffolding. Correct anchors: Phi = 0.008 Wb for x in [0.1,0.3] m; dPhi/dx = 0.04 Wb/m; emf magnitude 0.12 V; current magnitude 0.06 A; counterclockwise under the stated inward field. Explain that motion changes flux despite a static field, and that the original 0.012 Wb leading-edge-area estimate is not the integral. These values apply to the stated fully immersed configuration.',
       rubric=rubric('Uses the moving-area integral correctly: Phi=0.008 Wb, not 0.012 Wb; field and orientation assumptions are respected.',
                     'Prompts target physical meaning of the chain rule and velocity dependence; worked anchors are 0.12 V and 0.06 A with correct units.',
                     'Explains counterclockwise current by opposition to increasing into-page flux, distinguishing signed emf from magnitude.',
                     'For each chosen conceptual step provides placement, prompt, deep explanation, shallow response and contingent follow-up.',
                     'Provides a usable quality framework and progressively structured scaffolds without endorsing incorrect physics.'))
ACCEPTANCE.append({'dataset':'original42','task_id':tid,'positive_answer_anchor':'Phi=0.008 Wb, |emf|=0.12 V, |I|=0.06 A, counterclockwise.',
                   'negative_answer_example':'Phi=L*w*B(leading edge)=0.012 Wb is the exact nonuniform-field integral.',
                   'acceptance_method':'analytic integral and independent numerical quadrature; direction from explicit convention',
                   'independent_subject_review':'pending'})

# Supply the missing identifiability assumptions and avoid a predetermined orphan verdict.
tid='lesson-builder__03'
change('original42',tid,'仅凭发病数不能无条件确定 R0；未给定课时；评分预设历史讨论一定不相关。',
       context='A 90-minute graduate epidemiology seminar with 25 students. All incidence data below are synthetic teaching data, not observations from the 1918 pandemic.',
       user_prompt='''Build a complete 90-minute lesson package for 25 graduate epidemiology students: a timed plan, lecture notes, slide outline and active-learning segment. Outcomes: formulate the standard frequency-dependent SIR model and estimate R0 from early epidemic growth under explicit assumptions.
Use synthetic daily-incidence levels of 10, 20, 40 and 80 cases/day at days 0, 3, 6 and 9. Assume a closed, initially susceptible population (S/N approximately 1), homogeneous mixing, constant reporting and parameters, and an exponentially distributed infectious period with mean 4 days. Use dI/dt = beta*S*I/N - gamma*I. Explain why incidence growth alone does not determine R0 without an infectious-period/generation-interval assumption.
Include a worked example and an activity with timing, groups, materials, launch instructions and a fallback. Include 15 minutes on the 1918 pandemic and public-health policy. Either explicitly connect that discussion to model assumptions/parameter changes and a learning check, or identify it as contextual enrichment with a proposed alignment adjustment. Do not claim that an instructor has confirmed a change in outcomes. Historical statistics are optional; flag uncertain figures clearly and do not invent city-specific mortality data. Include informative slide titles and accessible figure descriptions.''',
       expected_output='A feasible 90-minute package with all requested components and the 15-minute historical segment. Synthetic growth r=ln(2)/3 per day, gamma=1/4 per day, beta=r+gamma, and R0=beta/gamma=1+4*ln(2)/3 approximately 1.924 under the stated early-phase SIR assumptions. Distinguish incidence and prevalence and explain why the estimate is conditional. Accept either a justified alignment of the history segment to modeling outcomes or an explicit enrichment flag; do not require a fixed orphan label. Uncertain historical claims are flagged in plain language or a verification tag; omitting optional statistics is allowed.',
       rubric=rubric('Correctly derives the stated SIR equations and conditional R0 estimate of about 1.924, with the infectious-period, susceptibility and reporting assumptions.',
                     'Provides a coherent 90-minute plan including the requested 15-minute history discussion and practical time allocation.',
                     'Either substantiates the history segment\'s link to outcomes and assessment, or labels it as enrichment and proposes an alignment adjustment; does not assume approval.',
                     'Provides lecture notes and informative, accessible slide guidance; uncertain historical statistics are explicitly qualified, and invented statistics are not accepted.',
                     'Provides an actionable learning activity with timing, grouping, materials, launch instructions, answer guidance and a contingency.'))
ACCEPTANCE.append({'dataset':'original42','task_id':tid,'positive_answer_anchor':'r=ln(2)/3, gamma=.25, R0 approximately 1.924; estimate is conditional.',
                   'negative_answer_example':'R0 is 2 because case counts double, regardless of the infectious period.',
                   'acceptance_method':'symbolic SIR linearization and numerical substitution','independent_subject_review':'pending'})

# Case-level grading should not require exact magic tags for optional facts.
tid='lesson-builder__02';r=BYOLD[tid];rr=json.loads(r['rubric'])
rr[3]['description']='If uncertain real-world statistics are used, they are clearly flagged as needing verification in plain language or a verification tag. Fictional numbers are labelled synthetic. Do not penalize omitting optional real-world statistics or failing to use an exact tag syntax; invented facts presented as verified are unacceptable.'
change('original42',tid,'题面只要求标记不确定统计，评分却要求所有统计必须使用固定 VERIFY 标签。',
       expected_output='A clearly labelled synthetic rare-earth sourcing case with teaching notes, discussion arc, board plan and facilitation guidance aligned to both outcomes. Real-world statistics are optional. Clearly distinguish fictional data from factual claims and qualify uncertain factual claims; equivalent verification wording is acceptable.',rubric=json.dumps(rr,ensure_ascii=False))

# Repair a declared learning goal and add a checkable answer instead of prose only.
tid='differentiation-adapter__01';r=BYOLD[tid];rr=json.loads(r['rubric'])
rr[3]['description']='Verifies that students still calculate item subtotals, add the costs and subtract the total from $50; repeated addition or multiplication is acceptable. Correct totals are $6, $10 and $6, total $22 and change $28.'
change('original42',tid,'题目包含单价乘数量，但学习目标仅写加减；缺少数值验收锚点。',
       user_prompt=r['user_prompt'].replace('Solve multi-step addition and subtraction word problems.','Calculate item subtotals using multiplication or repeated addition, add costs and subtract to find change.'),
       expected_output=r['expected_output']+' The mathematical key is bread $6, cakes $10, muffins $6, total $22 and change $28. Keep the student-facing task unsolved; provide the key separately for the teacher.',
       rubric=json.dumps(rr,ensure_ascii=False))

# Openness must not be graded against a predetermined philosophical conclusion.
tid='socratic-questioning-sequence-generator__02';r=BYOLD[tid]
change('original42',tid,'要求开放讨论，参考答案却预设学生必须接受负面情绪的必要性。',
       expected_output='An open discussion guide examining benefits, costs, consent and uncertainty in memory erasure. Accept reasoned disagreement about the value of negative emotions; do not require a predetermined anti-erasure conclusion. Include question types, anticipated responses with contingent follow-ups, facilitation and reflection on leading questions.')

# Put hidden deliverable requirements into the shared question for both conditions.
VISIBLE = {
 'retrieval-practice-generator__01':'Label each question as free recall, cued recall or recognition, with most questions requiring free or cued recall.',
 'retrieval-practice-generator__02':'Label retrieval types and use at least two questions to probe the two named misconceptions.',
 'socratic-questioning-sequence-generator__01':'Use at least four questions, two or three anticipated responses per question, and identify at least two places where leading wording should be avoided.',
 'socratic-questioning-sequence-generator__02':'Use at least five questions, label their inquiry types, provide two or three anticipated responses with follow-ups per question, and identify at least two risks of leading wording.',
 'socratic-questioning-sequence-generator__03':'Use at least six questions, label inquiry types, provide two or three anticipated responses with follow-ups per question, and identify at least two risks of leading wording.',
 'self-efficacy-builder-sequence__01':'Organize the plan into four to six achievable tasks, with success and difficulty-response scripts for each.',
 'self-efficacy-builder-sequence__02':'Organize the progression into four to six achievable tasks, with concrete feedback scripts and a maintenance plan.',
 'self-efficacy-builder-sequence__03':'Organize the progression into four to six achievable tasks, with feedback scripts and a maintenance plan; do not assume improvement has already occurred.',
 'lesson-builder__01':'Include duration, group size, materials, a launch script, a likely failure and contingency, and accessibility considerations for the lecture hall.',
 'lesson-builder__02':'Include a board plan and ways to distribute participation fairly in the discussion.',
 'adaptive-hint-sequence-designer__01':'Include an overview, hint text, cognitive purpose, triggers, expected student response and escalation for each level, followed by a trigger summary and adaptation notes. Equivalent section names are acceptable.',
 'self-explanation-prompt-designer__01':'Choose two to four insertion points and distinguish deep, partial and shallow explanations in the quality framework.',
 'emergent-project-design-scaffold__01':'Include a provisional four-phase scaffold (launch, investigate, represent, share/conclude), at least three provocations, and at least three observation-based decision points.',
 'emergent-project-design-scaffold__02':'Include a provisional four-phase scaffold (launch, investigate, represent, share/conclude) and at least three provocations with branching next steps.',
 'emergent-project-design-scaffold__03':'Include a provisional four-phase scaffold (launch, investigate, represent, share/conclude), at least four provocations across the inquiry strands, and multiple ways for children to represent their thinking.',
 'project-brief-designer__01':'Use three to five milestones; include student deliverables, instruction, formative checks and choice, plus process/product assessment, differentiation and revision.',
 'project-brief-designer__02':'Use three to five milestones; include student deliverables, instruction, formative checks and choice, plus process/product assessment, differentiation and revision.',
 'project-brief-designer__03':'Use three to five milestones; include deliverables, instruction, formative checks and choice, plus differentiation and revision. Treat any prototype as a classroom demonstration, not approved storage for real medicines.',
 'spaced-practice-scheduler__02':'Give every topic at least one retrieval opportunity in the final week before assessment.',
 'spaced-practice-scheduler__03':'After a topic is first taught, do not leave more than three weeks without retrieval. A first-session prerequisite diagnostic is acceptable before there is module content to revisit.',
}
for tid,extra in VISIBLE.items():
    current=PATCHES.get(('original42',tid),{}).get('user_prompt',BYOLD[tid]['user_prompt'])
    change('original42',tid,'将原本只藏在参考答案或评分标准中的交付要求写入双方共同题面。',user_prompt=current+'\n\nOutput requirements: '+extra)

# Eliminate contradictory and absolute assessment conditions.
tid='retrieval-practice-generator__01';r=BYOLD[tid];rr=json.loads(r['rubric'])
rr[2]['description']='Most items require reconstructing conceptual or procedural knowledge. Recognition items are allowed in the minority, but should require a justification or error explanation rather than reward surface cues alone.'
change('original42',tid,'允许 recognition 题，同时又要求每题都不能靠 recognition，标准自相矛盾。',rubric=json.dumps(rr,ensure_ascii=False))
for tid in ['hinge-question-designer__01','hinge-question-designer__02','hinge-question-designer__03']:
    r=BYOLD[tid];rr=json.loads(r['rubric'])
    rr[1]['description']=rr[1]['description'].replace('The correct answer cannot be arrived at through flawed reasoning or test-taking shortcuts.','Avoid obvious answer cues and explain the reasoning the item is intended to diagnose; a single multiple-choice response cannot rule out guessing.').replace('The correct answer cannot be guessed without conceptual understanding.','Avoid obvious answer cues; do not claim that guessing the correct answer is impossible.')
    if tid.endswith('__01'):
        rr[0]['description']=rr[0]['description'].replace('tests only the single concept of photosynthesis reactants/location','targets a clearly specified concept about photosynthesis inputs or location; if both are combined, explains the limits of inferring the source of an error')
    change('original42',tid,'选择题不能保证无法猜中；光合作用的原评分还把反应物和发生部位写成同一个概念。',rubric=json.dumps(rr,ensure_ascii=False))

# Topic-specific repairs for the extended set. Each entry has an independently checkable anchor.
GEOMETRY = [
 ('line-plane perpendicularity','A line perpendicular to two intersecting lines in a plane is perpendicular to the plane. Perpendicularity to just one in-plane line is insufficient; for plane z=0, the x-axis is perpendicular to the y-axis but lies in the plane.', 'Work backward from the goal, identify two intersecting in-plane lines, ask students which perpendicular relations are known or need construction, then verify both before invoking the theorem.', 'Using the line-plane parallel criterion, or using only one perpendicular line.'),
 ('plane-plane parallelism','Two distinct planes are parallel if two intersecting lines of one plane are respectively parallel to two intersecting lines of the other. One pair alone is insufficient: planes z=0 and y=0 share an x-direction but intersect.', 'Ask students to locate two independent directions and prove the corresponding relations; explicitly rule out coincident planes.', 'Claiming one parallel line pair alone proves planes parallel.'),
 ('plane-plane perpendicularity','If one plane contains a line perpendicular to the other plane, the planes are perpendicular. Perpendicular planes do not make every line in one perpendicular to the other.', 'Work backward to a perpendicular line, construct or identify it and verify its line-plane criterion; use planes x=0 and z=0 to show a shared in-plane direction is not a normal.', 'Answering with plane parallelism or claiming all lines in perpendicular planes are mutually perpendicular.'),
 ('three perpendiculars theorem','Let A lie outside plane alpha, O be its orthogonal projection, B be in alpha with B!=O, and l be an in-plane line through B. Then l is perpendicular to AB iff l is perpendicular to OB. OA is perpendicular to alpha and OB is the nonzero projection of AB.', 'Draw and label A,O,B,l, verify the projection conditions before using either implication, and justify via vector decomposition or a valid geometric proof.', 'Using the theorem without the projection or nonzero-projection conditions.'),
 ('law of cosines','For sides a,b,c opposite A,B,C, c^2=a^2+b^2-2ab*cos(C). SAS selects the included angle; SSS gives cos(C)=(a^2+b^2-c^2)/(2ab). For a=3,b=4,C=90 degrees, c=5.', 'Contrast SAS and SSS, let students choose the target side/angle and formula, check triangle feasibility and verify the numerical example.', 'Proving line-plane parallelism instead of choosing a triangle-solving formula.'),
 ('law of sines','a/sin(A)=b/sin(B)=c/sin(C)=2R for a nondegenerate triangle. Use opposite side-angle pairs, known angle sums and the sine rule; SSA can have two solutions and inverse sine alone is insufficient.', 'Use A=30 degrees,a=5,b=8: sin(B)=0.8, so test both B about 53.13 and 126.87 degrees against the angle sum.', 'Always treating arcsin as the unique SSA solution.'),
 ('converse of Pythagoras','For a triangle with longest side c, if a^2+b^2=c^2, the angle opposite c is right. Verify positive sides and triangle inequality; 3,4,5 qualifies while 2,3,4 does not.', 'Choose the longest side, calculate both sides of the equality and state the exact opposite angle; use a counterexample to an arbitrary side ordering.', 'Checking the equality against a non-longest side or treating the direct theorem as a proof of its converse.'),
 ('midsegment construction','In triangle ABC, if M,N are the midpoints of AB,AC then MN is parallel to BC and MN=BC/2. The required midpoint hypotheses must be established; being points on the sides is not enough.', 'Work backward from the desired parallel/half-length relation, locate the relevant triangle and midpoints, connect them, and prove before invoking the theorem.', 'Declaring any segment joining two side points a midsegment.'),
 ('vector collinearity','For b!=0, vectors a and b are linearly dependent iff a=lambda*b for some scalar lambda. In 2D the determinant a_x*b_y-a_y*b_x=0 avoids invalid divisions by zero; distinguish nonzero direction vectors of lines from the zero vector.', 'Use (0,2) and (0,5) as a valid vertical example, and (1,0),(0,1) as a nonexample; translate endpoint coordinates into direction vectors before testing.', 'Using component ratios that divide by zero or treating zero as a usable line direction.'),
]
for i,(topic,key,teach,bad) in enumerate(GEOMETRY,1):
    tid=f'lesson-builder__cn24_{i:02}'
    specific(tid,key,teach,bad,'题面换成了另一条定理，背景和参考答案仍固定讲线面平行。',
             context=f'A senior-secondary mathematics teacher wants students to understand how to choose and justify a construction or method for {topic}. No diagram is supplied. Introduce a clearly specified example, distinguish assumptions from conclusions, and make the search process visible. Only address this case\'s requested topic.')

specific('lesson-builder__cn25_01',
 'Here principal-variable method means treating a multivariable expression as a function of one chosen variable while other variables act as parameters. For x,y>=0 and x+y=6, xy=x*(6-x)=9-(x-3)^2 on 0<=x<=6, so the maximum is 9 at x=y=3. The constraint and chosen variable must be explicit.',
 'For average Grade 12 students compare a familiar trial/table approach with completing the square, explain why choosing x helps, check endpoints and give a nearby transfer example. This is one introductory illustration, not a claim that every multivariable problem reduces this way.',
 'Teaching Menelaus or segment ratios without addressing principal-variable selection.',
 '题面要求主元法，背景、答案和全部评分点却是梅涅劳斯定理。',
 context='A Grade 12 enrichment lesson for average-ability students. Principal-variable method here means choosing one variable as the main variable and treating the others as parameters or eliminating them using a constraint. Students know quadratic functions and completing the square. Design an accessible introduction, not an unexplained contest shortcut.')

VARIANTS = [
 ('function domains','For (x-2)/(x^2-4), the original domain excludes both -2 and 2 even after cancellation. For sqrt(x-1)/(x-2), require x>=1 and x!=2. State all original denominator/radical/log conditions before simplifying.','Canceling a factor and reinstating an excluded input.'),
 ('AM-GM equality','For a,b>=0, (a+b)/2>=sqrt(ab), with equality iff a=b. For x>0, x+4/x>=4 with equality at x=2. Applying the square-root form to arbitrary negative terms is invalid.','Claiming equality without testing attainability, or applying the stated inequality outside its domain.'),
 ('quadratic root location','Assume a!=0. A discriminant establishes real roots, not their positions. To locate roots use roots/vertex/endpoints with boundary cases. x^2-5x+6 has roots 2,3, so Delta>0 alone does not imply roots in (0,1). x^2-x+3/16 has roots 1/4,3/4 in (0,1).','Using only Delta>0 to certify an interval location.'),
 ('trigonometric signs','sin(pi-theta)=sin(theta), cos(pi-theta)=-cos(theta), sin(-theta)=-sin(theta). Track function, quadrant and sign; for theta=pi/6, cos(5*pi/6)=-sqrt(3)/2.','Dropping the quadrant sign or treating every trigonometric function as odd.'),
 ('sequence monotonicity','For a real sequence compare a_(n+1)-a_n on the stated index domain. Ratio tests require sign assumptions; a_n=-1/n for n>=1 increases although a_(n+1)/a_n=n/(n+1)<1.','Inferring decrease from ratio<1 for a negative sequence.'),
 ('line-circle position','For line Ax+By+C=0 with A^2+B^2>0 and circle center (h,k),radius r>0, compare |Ah+Bk+C|/sqrt(A^2+B^2) with r. For center (1,2),r=3, x=4 is tangent and x=1 is secant.','Using the distance from the origin when the center is not the origin, or omitting absolute value.'),
 ('binomial versus term coefficient','In (2x-1)^3=8x^3-12x^2+6x-1, the x^2 term has coefficient -12 whereas its binomial coefficient is C(3,1)=3. Include sign and scalar powers.','Giving 3 as the x^2 coefficient or ignoring the negative factor.'),
 ('vector conditions','For planar vectors, determinant zero tests linear dependence and dot product zero tests orthogonality. (0,2),(0,5) are dependent, while (0,2),(3,0) have zero dot product. Distinguish algebraic zero-vector cases from angles or directions of nonzero geometric vectors.','Dividing by a zero component or equating dot product zero with parallelism.'),
]
for i,(topic,key,bad) in enumerate(VARIANTS,1):
    specific(f'retrieval-practice-generator__cn23_{i:02}',key,
             f'Provide one three-item set about {topic}: an explicit misconception trap, a disguised application and a flawed-solution repair. Include correct answers, the condition each item probes and a short teacher follow-up.',
             bad,'一道题只问一个知识点，参考答案却强制输出八个主题的整套题组。')

OPENINGS = [
 ('law of sines','For a nondegenerate triangle a/sin(A)=b/sin(B)=c/sin(C). Motivate it by an oblique triangle and relate the ratio to an altitude or circumcircle. AAA fixes shape but not size; SSA can give zero, one or two triangles.','Use an oblique triangle with known opposite side-angle pair, compare an altitude-based solution with the new relationship, then check a second triangle and an SSA ambiguity.','A compulsory derivative/complex-number/logarithm lesson or a claim that every SSA triangle is unique.'),
 ('derivatives','Instantaneous rate is the limit of difference quotients, not substitution h=0 into a 0/0 expression. For s(t)=t^2, (s(t+h)-s(t))/h=2t+h for h!=0, whose limit is 2t.','Have students calculate shrinking-interval average rates at t=2, articulate the limit and distinguish average rate from instantaneous rate; use a transfer check.','Dividing by zero to compute the derivative or grading the lesson by triangle-congruence checks.'),
 ('complex numbers','x^2+1=0 has no real solution; extending the number system with i^2=-1 gives solutions i and -i. This is an extension of real numbers, not evidence that the original real solution set was nonempty.','Create the real-number impasse, define i consistently, verify both roots and compare with x^2-1=0.','Claiming one real solution or requiring sine-law SSA examples for this topic.'),
 ('logarithms','For a>0,a!=1,b>0, log_a(b) is the exponent x satisfying a^x=b. For 2^x=7, 2<x<3; the logarithm names the exact exponent without promising an elementary integer expression.','Compare solvable integer powers with 2^x=7, motivate inverse reasoning, state domain/base restrictions and check log_2(8)=3.','Using zero/negative log arguments in the real setting or requiring a four-topic lesson.'),
]
for i,(topic,key,teach,bad) in enumerate(OPENINGS,1):
    specific(f'lesson-builder__cn28_{i:02}',key,teach,bad,'单主题问题的参考答案要求讲四个主题，并把三角形验收条件套到其他主题。')

COUNTING = [
 ('Identical balls into k labelled boxes','For n>=0,k>=1, allowing empty boxes gives C(n+k-1,k-1); requiring every box nonempty gives C(n-1,k-1) when n>=k, otherwise zero. For n=4,k=3 the counts are 15 and 3.','Use stars and separators to explain a bijection, explicitly separate empty/nonempty cases and compare with labelled balls.','Using k^n for identical balls or silently assuming all boxes are nonempty.'),
 ('Distinct balls into identical boxes','Partitioning n labelled objects into exactly k nonempty unlabelled groups gives S(n,k); into at most k gives sum from j=0 to k of S(n,j). For n=3,k=2 there are 3 exact-two partitions and 4 at-most-two partitions.','List the small partitions and explain why permuting group labels does not create a new partition; state whether empty boxes are allowed.','Multiplying by k! for identical boxes or confusing exactly k with at most k.'),
 ('Derangements','For n labelled items and n matching labelled positions with no fixed point, D_n=n!*sum from j=0 to n of (-1)^j/j!. D_3=2 and D_4=9. Other restrictions require their own counting model.','List all n=3 permutations, identify forbidden fixed points, then motivate inclusion-exclusion; explain why subtracting n from n! fails.','Using n!-n or applying the derangement formula to unspecified unrelated restrictions.'),
 ('Labelled balls into labelled boxes','With n labelled balls and k labelled boxes, empty boxes allowed and no capacity restriction, every ball independently chooses one of k boxes: k^n. For n=3,k=2 there are 8 assignments.','Use a choice tree or function mapping and contrast with indistinguishable balls and with a nonempty-box requirement.','Using stars-and-bars or requiring each box to be nonempty without stating it.'),
 ('Adjacency restrictions','For five distinct objects A,B,C,D,E in a line, A and B adjacent gives 2*4!=48; nonadjacent gives 5!-48=72. Block internal order and gap counts depend on which objects are labelled.','Explain the block method and complement or gap method, and include a small transfer variation with the constraints stated.','Forgetting the AB/BA order or treating every nonadjacency problem as the same formula.'),
 ('Circular versus linear permutations','For n distinct objects around an oriented circle where rotations are equivalent but reflections are distinct, count (n-1)!; for n=4, 6 versus 24 in a line. A reflection-equivalent necklace or a table with labelled seats is a different problem.','Fix a reference object to justify rotation equivalence, draw examples of rotations and reflections, then test the changed convention.','Dividing by 2 without a reflection convention or applying (n-1)! to labelled seats.'),
 ('Group then distribute','Partition six labelled people into two unlabelled groups of three: C(6,3)/2=10. Assign those groups to two labelled rooms: 10*2!=20=C(6,3). Dividing by a factorial is justified only for genuine symmetry.','Represent one concrete allocation both ways and explain exactly what is counted twice before division.','Blindly dividing by k! when groups already have distinct labels or sizes.'),
 ('Binomial coefficients','In (2x-1)^3 the coefficients are 8,-12,6,-1, while the binomial coefficients are 1,3,3,1. The x^2 coefficient is C(3,1)*2^2*(-1)=-12.','Choose a term from each factor, connect the count of choices to C(n,k) and keep scalar/sign factors separate.','Reporting the binomial coefficient as the whole term coefficient.'),
]
for i,(topic,key,teach,bad) in enumerate(COUNTING,1):
    specific(f'lesson-builder__cn31_{i:02}',key,teach,bad,'单个计数主题被要求回答八类问题；同时缺少可核验的计数值和条件约定。')

# Each classroom scenario gets its own decision and evidence requirements.
PRACTICAL = [
 ('A sinking paper clip is an observation, not a failed student. Surface support depends on placement, surface condition and wetting; flotation is not guaranteed.', 'Say what was observed, invite one testable explanation, and compare gentle placement in clean water with the original attempt.', 'Promising every paper clip floats or replacing observations with the textbook result.'),
 ('Immobile earthworms do not establish a moisture preference. Acclimation, lighting, temperature and moisture can affect behavior.', 'Allow observation time, compare conditions while changing one factor and protect the organisms; record no movement honestly.', 'Forcing movement, drying organisms deliberately or interpreting immobility as a clear choice.'),
 ('Check whether the facing ends really are like poles and whether both objects are magnets before revising the claim about poles.', 'Label ends consistently and use a known magnet to check the pole identification, then repeat and document.', 'Declaring magnetism disproved or changing the recorded result to match a textbook.'),
 ('Failure to extinguish the candle does not identify a unique cause: gas quantity, mixing and delivery are hypotheses, not observed facts.', 'Acknowledge uncertainty, record setup and propose one controlled comparison; any flame demonstration is teacher-managed and gas is not trapped in a sealed vessel.', 'Inventing a certain cause or requiring children to reproduce flames at home.'),
 ('One week without visible bending does not show that plants never respond to light. Directional light, growth and observation conditions need checking.', 'Compare documented light conditions and growth over time with otherwise similar plants; make a prediction before observing.', 'Guaranteeing a bend by a fixed date or dismissing the observation.'),
 ('Touch may damp a tuning fork and weak vibration can be hard to feel. A teacher can state the scientific explanation while distinguishing it from the evidence students observed.', 'Pair the explanation with a visible vibration indicator or an appropriate demonstration and a short follow-up check.', 'Claiming an unfelt vibration disproves sound vibration, or banning all direct explanation.'),
 ('For a small-amplitude ideal pendulum, T=2*pi*sqrt(L/g), independent of bob mass. Length runs from pivot to the center of mass.', 'Control effective length and release amplitude, time several oscillations and repeat before comparing masses; discuss measurement uncertainty.', 'Using bob mass as the ideal-period cause or altering measurements to match theory.'),
 ('A bulb needs an intact closed low-voltage circuit connecting its two contacts to the source. Contacts, bulb and battery are separate possible faults.', 'Offer graduated checks of one component at a time, beginning with the complete path; use only classroom low-voltage equipment and avoid short circuits.', 'Inferring inability from failure or recommending mains electricity.'),
 ('Rust rates depend on exposure and material conditions, including moisture, oxygen and coatings; identical rates are not guaranteed.', 'Compare the groups\' condition records, identify confounds and agree on a controlled follow-up while retaining the different observations.', 'Discarding slow-rusting samples as wrong or assuming one universal rate.'),
 ('A ketchup volcano is a model whose behavior depends on its stated mechanism; do not assume an unspecified acid-base reaction.', 'Assign a drawing, prediction and one safe unsealed model comparison with an adult where needed; distinguish the model from real magma.', 'Increasing pressure in a sealed container or equating ketchup flow with real volcanic mechanisms.'),
]
for i,(key,teach,bad) in enumerate(PRACTICAL,1):
    specific(f'adaptive-hint-sequence-designer__cn59_{i:02}',key,teach,bad,
             '不同实验共用摆锤的参考答案，评分要求与学生实际遇到的问题不对应。')

ASSESSMENT = [
 ('A paper-and-pencil process record can track prediction, observation and evidence-based explanation of changes of state.', 'Give a one-page third-grade checklist with a concrete observation field, a short feedback box and a revision opportunity; respect the no-computer constraint.', 'Requiring an online platform or scoring only the final result.'),
 ('The simplest useful template links a learning target to an observable action, recorded evidence, feedback and a next attempt.', 'Provide a reusable small table and one completed example, beyond Excellent/Good/Average labels.', 'Giving only a rank with no evidence or improvement step.'),
 ('Self-assessment needs shared criteria and examples; a high self-score alone is not proof of dishonesty.', 'Calibrate one sample together, require students to cite their work and choose a supported improvement, then compare with a teacher check.', 'Automatically subtracting marks from every self-awarded full score.'),
 ('Peer feedback should name observed work, connect it to a criterion and suggest a feasible next step.', 'Model one specific comment, provide a short evidence-based sentence frame and let the recipient try a revision.', 'Requiring personal criticism or accepting generic praise as assessment evidence.'),
 ('Useful feedback names an observed strategy or action and a next step related to the goal.', 'Rewrite a generic praise sentence into a concrete example without inventing actual student performance.', 'Fixed ability labels or praise unrelated to observed work.'),
 ('Maintain accessible core goals while using scaffolds and individual progress evidence to support students who struggle.', 'Offer a small achievable next step, a supported retry and private progress feedback.', 'Fabricating full marks or repeatedly ranking the same students last.'),
 ('Assessment workload can be reduced by focusing on a few important criteria and rotating observation rather than documenting everything every lesson.', 'Give a manageable sampling and self/peer-check routine with targeted teacher review and identify its coverage limits.', 'Claiming unobserved pupils were assessed or adding a large daily documentation burden.'),
 ('A four-week lantern project needs evidence at design, construction, testing and revision milestones, not just a final product score.', 'Provide four weekly checkpoints, an individual contribution record and a feasible revision opportunity.', 'Returning a water-state experiment checklist without adapting it to the lantern project.'),
 ('Feedback becomes useful when students act on it and compare the revision with the original evidence.', 'Add a bounded identify-correct-explain-recheck cycle and a teacher or peer verification step.', 'Collecting corrections without checking them or demanding endless retries.'),
 ('Participation can use multiple accessible presentation formats and rotating responsibilities while retaining individual evidence of learning.', 'Give a schedule, shared criteria and a way for each student to contribute without making polished public speaking the only route.', 'Selecting only top performers or equating group quality with every member\'s learning.'),
]
for i,(key,teach,bad) in enumerate(ASSESSMENT,1):
    specific(f'lesson-builder__cn51_{i:02}',key,teach,bad,
             '十种评价问题共用三态变化实验的模板，缺少针对本题的回答与验收点。')

TIERS = [
 ('No wording guarantees an AI-proof task. Assess authentic context evidence, reasoning and a short follow-up explanation rather than polished definitions alone.', 'Ask students to compare a familiar local service with a cloud service using non-sensitive observations and explain a choice; provide criteria and a checkable process record.', 'Guaranteeing AI cannot answer or requiring private school information.'),
 ('Repeated errors should trigger a supportive pause, a smaller diagnostic scaffold and teacher follow-up, not endless harder questions.', 'Describe a bounded automated branch with an accessible exit, neutral feedback, saved progress and an optional supported retry.', 'Permanent lockout, humiliation or a claim that one automated action suits every learner.'),
 ('A no-equipment task can assess interpretation and error diagnosis, but cannot certify knife skill.', 'Provide a small synthetic width table, e.g. target 3 mm and samples 2,3,5 mm with deviations -1,0,2; ask for a prediction, likely process cause and improvement in under 15 minutes, with an answer key.', 'Requiring knives or potatoes at home, a reflection essay, or claiming demonstrated practical mastery.'),
 ('A question-bank ledger should make responsibility and verification traceable.', 'Give exactly five useful fields: source/permission; learning target; level/prerequisites; verified answer/rationale; owner plus review status/time estimate. Explain the entry acceptance check.', 'Accepting unchecked copied questions or omitting the answer reviewer.'),
 ('Student time samples can reduce reliance on teacher estimates but remain noisy observations, not perfect surveillance.', 'Sample voluntary student start/end and active-work records, distinguish interruptions, report a distribution and provide an offline route; compare with the stated school 30-minute rule.', 'Claiming exact objective time from a click log or generalizing the school rule to every school.'),
 ('Correction should be bounded and explainable, with support and a pause option.', 'Use three steps: identify and explain an error; attempt one comparable item with support; receive feedback and save a next step or request teacher help.', 'Forcing unlimited retries or locking the student in the app until success.'),
 ('Small variations can reduce direct copying but cannot guarantee search or AI failure.', 'Give three low-cost techniques: change parameters and recompute the key; compare or diagnose two methods; require a contextual intermediate step. Show how to validate each new answer.', 'Promising apps fail immediately or changing numbers without updating the answer.'),
 ('Core work needs an accessible entry and support, alongside meaningful goals and extensions; difficulty should be informed by evidence, not labels.', 'Provide a firm but respectful staff script using a concrete scaffold and a way to monitor completion and understanding.', 'Predicting inevitable catastrophe or lowering every pupil\'s goal permanently to the current lowest performance.'),
 ('Reusable extension banks and flexible progression can reduce daily preparation, but setup and review still take time.', 'Offer three advanced students an optional deeper task pathway with checkpoint feedback and suitable existing reviewed resources.', 'Promising zero teacher workload or merely assigning more repetitive questions.'),
 ('Alignment needs a measurable learning objective and a mapping from task evidence to assessment criteria.', 'Provide exactly two form fields with one filled example showing what performance would demonstrate the stated objective.', 'Listing only topic names and question counts.'),
]
for i,(key,teach,bad) in enumerate(TIERS,1):
    tid=f'differentiation-adapter__cn62_{i:02}'
    prompt=None
    if i in (1,6,7,8,9):
        prompt=BYNEW[tid]['user_prompt']+'\nClarification: challenge absolute or coercive premises where necessary. Propose a feasible, bounded approach; no guarantee of AI-proofness, zero workload, or forced success is required.'
    specific(tid,key,teach,bad,'不同作业设计问题共用笼统评分点，部分题面要求无法保证或不合适的绝对效果。',prompt=prompt)

GROUPS = [
 ('The three estimates total 110 minutes. Coordination requires a stated overall budget and removal of redundant work, not an invented universal time cap.', 'Give a concise table for subject, objective, essential task, estimated/observed time, deadline and coordinating decision, plus a short staff script.', 'Reporting the sum incorrectly or declaring an unstated national limit.'),
 ('Four roles can cover operation, procedure checking, safety observation and recording. Actual machine operation is restricted to trained, authorized students under appropriate supervision.', 'Specify individual evidence and rotation within permitted roles; use simulation or demonstration when operational prerequisites are missing.', 'Forcing every untrained student to operate a CNC lathe to earn credit.'),
 ('An individual alternative should preserve the assessed core competencies and adapt the interaction format; family background alone does not justify lower expectations.', 'Map the group task objectives to an individual simulation, submitted decisions and private feedback, without requiring a clinical diagnosis.', 'Automatically lowering learning goals or forcing public disclosure of family or health details.'),
 ('First check participation evidence and barriers separately, then assign clear individual deliverables with a deadline and interim check.', 'Give a one-week intervention schedule, a support route and evidence-based individual credit; do not promise total prevention of free-riding.', 'Punishing based solely on an allegation or guaranteeing compelled participation.'),
 ('A defensible example is 60 percent individual process and 40 percent group outcome; weights need justification rather than a claim of perfect fairness.', 'List three evidence fields: attributable deliverable, version/change record, and a brief explanation or verification question. Explain how evidence supports the individual score.', 'Treating timestamps alone as proof of learning or counting all group output as each member\'s work.'),
 ('Authentic cost estimates may have justified ranges under different stated assumptions, so grading needs calibrated methods and reference examples.', 'Arrange qualified industry review of authorized materials, annotate assumptions and units, develop exemplars and a method/evidence rubric before grading.', 'Inventing one universal exact answer or outsourcing judgment without calibration.'),
 ('Progression can move from a supported basic joint to independently checking a circuit and then diagnosing a fault, with explicit prerequisites.', 'Use the same suitable training equipment, supervised unpowered practice where appropriate, common safety expectations and optional extension; assess observable evidence.', 'Using derogatory ability labels as fixed tracks or unsafe unsupervised powered work.'),
 ('Two useful required fields are criterion-linked observed evidence and the reason for the score with a specific improvement.', 'Give a completed example and calibrate scores against an anchor before the next peer review; acknowledge that fields alone cannot eliminate favoritism.', 'Guaranteeing impartiality merely by adding boxes.'),
 ('Reusable project questions need documented provenance, units, assumptions, cleaned data and a separately verified teacher key or defensible answer range.', 'Archive a versioned student package and teacher package, remove unnecessary personal information and pilot one task before reuse.', 'Publishing messy raw data as a validated bank or exposing the answer in the student handout.'),
 ('Practical and written tasks serve different objectives; explain their alignment and evidence without asserting all projects are superior.', 'Provide a respectful parent script with a concrete learning-and-assessment example; replace hazardous unsupervised manhole work with an approved safe simulation or observation.', 'Dismissing written learning, promising certificate success, or endorsing ordinary unsupervised student manhole opening.'),
]
for i,(key,teach,bad) in enumerate(GROUPS,1):
    tid=f'differentiation-adapter__cn63_{i:02}'
    prompt=None
    if i in (2,3,4,5,7,10):
        prompt=BYNEW[tid]['user_prompt']+'\nClarification: retain the learning goal but correct unsupported absolutes, stigmatizing labels or unsafe assumptions. Equivalent accessible assessment is acceptable; machine operation requires suitable training, authorization and supervision.'
    specific(tid,key,teach,bad,'合作任务共用泛化答案，缺少个体证据、题目条件和必要的适用边界。',prompt=prompt)


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    changes=[]; inventory=[]; counts={}; sources={}
    for dataset,name,fields,rows in [('original42','single_turn_tasks.csv',FIELDS42,OLD),('cn263','single_turn_tasks_cn263.csv',FIELDS263,NEW)]:
        patch_dataset=dataset
        revised=[]; changed_count=0
        sources[name]=digest((ROOT/'data'/name).read_bytes())
        for row in rows:
            key=(patch_dataset,row['task_id']); new=dict(row)
            edits=PATCHES.get(key,{})
            assert set(edits)<=set(fields),key
            new.update(edits)
            diff={f:{'before':row[f],'after':new[f]} for f in fields if row[f]!=new[f]}
            if diff:
                changed_count+=1
                changes.append({'dataset':dataset,'task_id':row['task_id'],'reasons':NOTES[key],
                                'before_sha256':row_digest(row),'after_sha256':row_digest(new),'fields':diff})
            inventory.append({'dataset':dataset,'task_id':row['task_id'],
                              'status':'revised_candidate' if diff else 'screened_not_accepted',
                              'changed_fields':','.join(diff),
                              'independent_review':'pending','live_evaluation':'not_run'})
            revised.append(new)
        counts[dataset]={'total':len(rows),'revised':changed_count,'unchanged':len(rows)-changed_count}
        with (OUT/name).open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(revised)
    assert all(tid in (BYNEW if ds=='cn263' else BYOLD) for ds,tid in PATCHES)
    for name,value in [('changes.json',changes),('acceptance_cases.json',ACCEPTANCE)]:
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (OUT/'review_inventory.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(inventory[0]));writer.writeheader();writer.writerows(inventory)
    trace=ROOT/'data/single_turn_tasks_cn263_trace.csv'
    (OUT/trace.name).write_bytes(trace.read_bytes());sources[trace.name]=digest(trace.read_bytes())
    artifacts={p.name:digest(p.read_bytes()) for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json'}
    manifest={'revision':'case-review-20260930','status':'candidate_not_released',
              'scope':'42 original and 263 expanded tasks; targeted corrections, not full semantic acceptance',
              'source_sha256':sources,'counts':counts,'artifacts_sha256':artifacts,
              'builder_sha256':digest(Path(__file__).read_bytes()),
              'limitations':['Independent subject review pending.','No model or judge calls performed.',
                             'Historical answers and scores do not become revised-case results.',
                             'Contrast examples are authored acceptance anchors, not independently passed judge tests.']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(counts,ensure_ascii=False))


if __name__=='__main__':
    build()
