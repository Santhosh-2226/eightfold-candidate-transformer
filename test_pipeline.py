import sys
sys.path.insert(0, '.')
from main_pipeline import run_pipeline

sources = {
    'csv':      'sample_data/recruiters.csv',
    'ats_json': 'sample_data/ats.json',
    'resume':   'sample_data/resume.txt',
    'notes':    'sample_data/notes.txt',
}

result = run_pipeline(sources)
print('TOTAL CANDIDATES:', len(result))

for c in result:
    print()
    print('NAME:', c.get('full_name'))

    exp = c.get('experience', [])
    print('  EXPERIENCE:', len(exp))
    for e in exp:
        print('   -', e.get('company'), '|', e.get('title'), '|', e.get('start'), '-', e.get('end'))

    edu = c.get('education', [])
    print('  EDUCATION:', len(edu))
    for e in edu:
        print('   -', e.get('institution'), '|', e.get('degree'), '|', e.get('field'), '| year:', e.get('end_year'), '| cgpa:', e.get('cgpa'))

    skills = [s['name'] for s in c.get('skills', [])]
    print('  SKILLS (' + str(len(skills)) + '):', skills)
    print('  years_exp:', c.get('years_experience'))
    print('  confidence:', c.get('overall_confidence'))

    prov = c.get('provenance', [])
    print('  PROVENANCE (' + str(len(prov)) + ' entries):')
    for p in prov[:4]:
        bd  = p.get('confidence_breakdown') or {}
        trace = p.get('normalization_trace') or ''
        print('   field:', p.get('field'),
              '| trust:', p.get('trust'),
              '| trace:', trace,
              '| R:', bd.get('reliability'), 'CP:', bd.get('conflict_penalty'), 'AB:', bd.get('agreement_boost'))
