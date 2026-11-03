from __future__ import annotations
import io
import json
import zipfile
from .store import one,root,all_rows


def markdown(report,image_prefix='images'):
    lines=['# '+report['title'],'',f"论文版本：{report['version_label']} · 阅读范围：{report['scope']} · {report['created']}",'',
        '原文：'+(report.get('source_url') or '本地导入 PDF'),'',report['quality_note'],'']
    lines.extend(['## 论文速览','',report.get('summary',''),''])
    for section in report.get('summary_sections',[]):
        for ref in section['evidence']:
            lines.extend([f"速览依据（{section['section']}）：PDF 第 {ref['page']} 页，块 {ref['block_id']}。",'', '> '+ref['quote'].replace('\n','\n> '),''])
    for item in report['items']:
        lines.extend(['## '+item['section'],'',{'author_claim':'作者报告','analysis':'系统分析','uncertain':'待确认'}[item['kind']]+'：'+item['text'],''])
        if not item['verified']:lines.extend(['> 引用尚未核对，请回原文确认。',''])
        for ref in item['evidence']:lines.extend([f"来源：PDF 第 {ref['page']} 页，块 {ref['block_id']}。",'', '> '+ref['quote'].replace('\n','\n> '),''])
    for fig in report['figures']:
        lines.extend(['## '+fig['label'],'',f"![原文第 {fig['page']} 页]({image_prefix}/page-{fig['page']}.png)",'',fig['description'],'','图注：'+fig['caption'],''])
    if report['warnings']:lines.extend(['## 阅读范围与待核对事项','']+['- '+w for w in report['warnings']])
    return '\n'.join(lines)


def export_zip(report_id,include_pdf=False):
    row=one('SELECT * FROM reports WHERE id=?',(report_id,))
    if not row:raise ValueError('报告不存在')
    report=json.loads(row['content']);buf=io.BytesIO()
    assessments=[json.loads(r['content']) for r in all_rows('SELECT content FROM assessments WHERE report_id=? ORDER BY created DESC',(report_id,))]
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('summary.md',markdown(report));z.writestr('report.json',json.dumps(report,ensure_ascii=False,indent=2))
        if assessments:
            z.writestr('assessments.json',json.dumps(assessments,ensure_ascii=False,indent=2))
            lines=['# 论文质量与阅读优先级','', '以下是各评分时点的记录；主题或论文变更后，历史评分不代表当前推荐顺序。','']
            for a in assessments:
                lines.extend(['## '+a['topic_name'],f"主题修订 {a['topic_revision']} · 规则 v{a['rubric_version']} · {a['created']}",f"阅读优先分：{a['priority_score']}；研究质量分：{a['quality_score']}",a['caveat'],''])
                for d in a['dimensions']:
                    lines.extend([f"### {d['label']}：{d['score']} / 5",d['reason'],''])
                    for ref in d['evidence']:lines.extend([f"原文 p.{ref['page']}：{ref['quote']}",''])
            z.writestr('assessment.md','\n'.join(lines))
        pages=set()
        for f in report['figures']:
            if f['page'] not in pages:
                z.write(root()/f['image'],f"images/page-{f['page']}.png");pages.add(f['page'])
        if include_pdf:
            v=one('SELECT pdf_path FROM versions WHERE id=?',(row['version_id'],))
            if v['pdf_path']:z.write(root()/v['pdf_path'],'source.pdf')
    return buf.getvalue()
