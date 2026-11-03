from __future__ import annotations
import re
import pymupdf
from .store import root, atomic_json


def extract(version,max_pages=100):
    folder=f"papers/{version['paper_id']}/{version['id']}"
    path=root()/version['pdf_path']
    with pymupdf.open(path) as doc:
        if doc.needs_pass:raise ValueError('暂不支持加密 PDF，请上传可读取的文件')
        if doc.page_count==0:raise ValueError('PDF 没有页面')
        pages=[];blocks=[];figures=[];warnings=[]
        total=doc.page_count
        for i in range(min(total,max_pages)):
            p=doc[i]
            page_blocks=[]
            for n,b in enumerate(p.get_text('blocks',sort=True)):
                if b[6]!=0 or not b[4].strip():continue
                text=b[4].strip()
                block={'id':f'p{i+1}b{n}','page':i+1,'bbox':list(b[:4]),'text':text}
                page_blocks.append(block);blocks.append(block)
                if re.match(r'^(?:Fig(?:ure)?\.?|Table|图|表)\s*\d+',text,re.I):
                    figures.append({'label':text.split('\n')[0][:100],'caption':text,'page':i+1,
                                    'block_id':block['id'],'mode':'page_preview','image':f'{folder}/pages/{i+1}.png'})
            page_path=f'{folder}/pages/{i+1}.png'
            (root()/page_path).parent.mkdir(parents=True,exist_ok=True)
            scale=min(1.6,1300/max(p.rect.width,p.rect.height))
            p.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False).save(root()/page_path)
            chars=sum(len(b['text']) for b in page_blocks)
            pages.append({'page':i+1,'chars':chars,'image':page_path,'block_ids':[b['id'] for b in page_blocks]})
            if chars<80:warnings.append(f'第 {i+1} 页文字较少，可能是图片页或扫描页，未执行 OCR')
        if total>max_pages:warnings.append(f'共 {total} 页，仅处理前 {max_pages} 页（当前设置上限）')
        result={'schema':1,'parser':'pymupdf-'+pymupdf.VersionBind,'total_pages':total,'processed_pages':len(pages),
                'pages':pages,'blocks':blocks,'figures':figures,'warnings':warnings,
                'reading_order':'按页面文字坐标排序，复杂多栏顺序需人工核对',
                'complete':total<=max_pages and not warnings}
    target=f'{folder}/extraction.json';atomic_json(target,result)
    return target,result


def chunks(extraction,limit):
    current=[];size=0
    for block in extraction['blocks']:
        # Split long blocks into addressable pieces; never silently truncate text.
        for n in range(0,len(block['text']),limit):
            text=block['text'][n:n+limit]
            if current and size+len(text)>limit:
                yield current;current=[];size=0
            current.append({**block,'text':text});size+=len(text)
    if current:yield current
