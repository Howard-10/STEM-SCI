"""Update demo_extract.py mock data to match new schema."""
import json, os

NEW_MOCK = {
    "10.1000/STEM001": json.dumps({"triples": [
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"USES_METHOD","tail":"quasi-experimental design","tail_type":"ResearchMethod","evidence":"This study employed a quasi-experimental design with 172 undergraduate physics students","confidence":1.0,"layer":"L2"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"USES_METHOD","tail":"project-based learning","tail_type":"PedagogicalMethod","evidence":"effect of project-based learning integrated with ChatGPT","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"DEPLOYS_TECH","tail":"ChatGPT","tail_type":"Technology","evidence":"project-based learning integrated with ChatGPT","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"STUDIES_DOMAIN","tail":"thermodynamics","tail_type":"SubjectDomain","evidence":"conceptual understanding of thermodynamics","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"TARGETS_OUTCOME","tail":"conceptual understanding","tail_type":"LearningOutcome","evidence":"significantly outperformed the control group on the Thermodynamics Conceptual Understanding Test","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"TARGETS_OUTCOME","tail":"student engagement","tail_type":"LearningOutcome","evidence":"Students reported increased engagement","confidence":0.90,"layer":"L2"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"TARGETS_OUTCOME","tail":"self-efficacy","tail_type":"LearningOutcome","evidence":"increased engagement and self-efficacy","confidence":0.90,"layer":"L2"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"INVOLVES_POPULATION","tail":"undergraduate students","tail_type":"StudentPopulation","evidence":"172 undergraduate physics students","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"HAS_SAMPLE","tail":"N=172, experimental n=86, control n=86","tail_type":"SampleInfo","evidence":"172 undergraduate physics students ... experimental group (n=86) [...] control group (n=86)","confidence":1.0,"layer":"L2"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"HAS_EFFECT_SIZE","tail":"d=0.82","tail_type":"EffectSize","evidence":"d=0.82, p<0.01","confidence":1.0,"layer":"L3"},
        {"head":"10.1000/STEM001","head_type":"Paper","relation":"CLAIMS","tail":"AI-integrated PBL improves thermodynamics conceptual understanding","tail_type":"Claim","evidence":"AI-integrated PBL can effectively improve physics learning outcomes","confidence":0.90,"layer":"L2"},
    ]}),
    "10.1000/STEM002": json.dumps({"triples": [
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"USES_METHOD","tail":"systematic review","tail_type":"ResearchMethod","evidence":"Following PRISMA guidelines, we conducted a systematic review of 44 empirical studies","confidence":1.0,"layer":"L2"},
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"USES_METHOD","tail":"PRISMA","tail_type":"ReportingGuideline","evidence":"Following PRISMA guidelines","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"DEPLOYS_TECH","tail":"virtual reality","tail_type":"Technology","evidence":"systematic review of 44 empirical studies on VR applications in physics education","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"STUDIES_DOMAIN","tail":"mechanics","tail_type":"SubjectDomain","evidence":"VR is most frequently applied in mechanics (38%)","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"STUDIES_DOMAIN","tail":"electromagnetism","tail_type":"SubjectDomain","evidence":"mechanics (38%) and electromagnetism (27%)","confidence":0.90,"layer":"L2"},
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"USES_METHOD","tail":"inquiry-based learning","tail_type":"PedagogicalMethod","evidence":"most common pedagogical approaches integrated with VR are inquiry-based learning and game-based learning","confidence":0.90,"layer":"L2"},
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"USES_METHOD","tail":"game-based learning","tail_type":"PedagogicalMethod","evidence":"inquiry-based learning and game-based learning","confidence":0.90,"layer":"L2"},
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"TARGETS_OUTCOME","tail":"conceptual understanding","tail_type":"LearningOutcome","evidence":"moderate overall effect on conceptual understanding","confidence":0.90,"layer":"L2"},
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"HAS_EFFECT_SIZE","tail":"Hedges g=0.65","tail_type":"EffectSize","evidence":"Hedges g=0.65","confidence":1.0,"layer":"L3"},
        {"head":"10.1000/STEM002","head_type":"Paper","relation":"CLAIMS","tail":"VR effectively visualizes abstract physics phenomena","tail_type":"Claim","evidence":"VR was particularly effective for visualizing abstract phenomena such as electric fields and wave propagation","confidence":0.90,"layer":"L3"},
    ]}),
    "10.1000/STEM003": json.dumps({"triples": [
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"USES_METHOD","tail":"mixed-methods","tail_type":"ResearchMethod","evidence":"This mixed-methods study examined","confidence":1.0,"layer":"L2"},
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"DEPLOYS_TECH","tail":"generative AI","tail_type":"Technology","evidence":"generative AI feedback affects pre-service science teachers modelling competence","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"USES_METHOD","tail":"AI-powered scaffolding","tail_type":"PedagogicalMethod","evidence":"AI scaffolding can serve as an effective cognitive tool","confidence":0.85,"layer":"L2"},
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"INVOLVES_POPULATION","tail":"pre-service science teachers","tail_type":"StudentPopulation","evidence":"64 pre-service science teachers participated","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"TARGETS_OUTCOME","tail":"scientific modelling competence","tail_type":"LearningOutcome","evidence":"significant improvement in modelling competence","confidence":0.95,"layer":"L2"},
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"HAS_SAMPLE","tail":"N=64, 12-week intervention","tail_type":"SampleInfo","evidence":"64 pre-service teachers participated in a 12-week intervention","confidence":1.0,"layer":"L2"},
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"HAS_EFFECT_SIZE","tail":"d=0.94","tail_type":"EffectSize","evidence":"Pre-post tests showed significant improvement in modelling competence (d=0.94)","confidence":1.0,"layer":"L3"},
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"CLAIMS","tail":"generative AI feedback improves pre-service teachers modelling competence","tail_type":"Claim","evidence":"AI feedback helped students identify misconceptions and refine model structures","confidence":0.90,"layer":"L3"},
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"TARGETS_OUTCOME","tail":"misconception identification","tail_type":"LearningOutcome","evidence":"AI feedback helped students identify misconceptions","confidence":0.85,"layer":"L2"},
        {"head":"10.1000/STEM003","head_type":"Paper","relation":"EMPLOYS_ASSESSMENT","tail":"pre-post test","tail_type":"Assessment","evidence":"Pre-post tests showed significant improvement","confidence":0.90,"layer":"L2"},
    ]}),
}

# Update demo_extract.py
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_extract.py")
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

start = content.index("MOCK_PROFILE_RESPONSES = {")
depth = 0
end = start
for i in range(start, len(content)):
    if content[i] == "{":
        depth += 1
    elif content[i] == "}":
        depth -= 1
        if depth == 0:
            end = i + 1
            break

new_dict = "MOCK_PROFILE_RESPONSES = " + json.dumps(NEW_MOCK, indent=4, ensure_ascii=False)
content = content[:start] + new_dict + content[end:]

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

counts = {k: len(json.loads(v)["triples"]) for k, v in NEW_MOCK.items()}
print(f"Updated demo mock data. Papers: {list(NEW_MOCK.keys())}, Triples: {counts}")
