import json
import re
from pathlib import Path
from unittest.mock import MagicMock
import shutil
import subprocess

import pandas as pd
import pytest
from sqlalchemy.engine import make_url

from app import create_app
from config import Config
from data import db
from areas.adm.desconexao import dash_executivo as executivo
from areas.adm.desconexao import dash_log as log
from areas.adm.desconexao import dash_backlog as backlog
from areas.adm.desconexao import dash_parceiras as parceiras
from areas.adm.desconexao import dash_quebra as quebra
from areas.adm.desconexao import dash_safra_v8 as safra
from routes import dash_retirada as retirada


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(db, 'get_engine', lambda: pytest.fail('Teste tentou acessar banco real'))
    return create_app({'TESTING': True, 'PRELOAD_DATA': False})


@pytest.fixture
def frame():
    return pd.DataFrame({
        'SAFRA': ['1 MES', '4 MESES', '1 MES'],
        'DS_TIPO_DESCONEXAO': ['INAD', 'OPCAO', 'INAD'],
        'NM_CIDADE': ['MANAUS', 'BELEM', 'MANAUS'], 'UF': ['AM', 'PA', None],
        'PENDENCIA': ['RECUPERADO', 'PENDENTE', None],
        'STATUS_OPERACIONAL': ['EM ANDAMENTO', None, 'CRITICO'],
        'ULT_PARCEIRA': ['A', 'B', 'A'], 'PARCEIRA_NOME': ['A', 'B', 'A'],
        'FAIXA_LOG': ['1x', 'SEM LOG', None],
        'ANL_MOTIVO_REAGENDA': ['CLIENTE AUSENTE', None, None],
        'ANL_QUEBRA_RESPONSAVEL': ['CLIENTE', None, None],
        'TEM_TOA': ['SIM', 'SIM', 'NAO'], 'TEM_ANALITICO': ['SIM', 'NAO', 'SIM'],
        'TEM_BACKLOG': ['SIM', 'SIM', 'NAO'], 'TOA_STATUS': ['concluído', 'pendente', None],
        'SITUACAO_AGENDA': ['EXECUTADA', 'COM QUEBRA', 'SEM ANALITICO'],
        'BKL_DATA_AGENDAMENTO': ['2026-09-01', '2026-09-02', None],
        'BKL_TEMPO_ABERTURA_DIAS': [2, 20, None],
    })


def test_pages_and_internal_links(app, monkeypatch):
    monkeypatch.setattr(executivo, 'get_options', lambda: {})
    client=app.test_client()
    pages=['/', '/area/adm', '/area/adm/desconexao/', '/area/adm/seguranca', '/area/omr']
    pages += [f'/dash/{name}/' for name in ['executivo','log','parceiras','backlog','quebra','retirada','safra']]
    for page in pages:
        response=client.get(page)
        assert response.status_code == 200, page
        for link in re.findall(r'href="(/[^"?#]*)"', response.text):
            assert client.get(link, follow_redirects=True).status_code == 200, (page, link)
    assert client.get('/area/inexistente/em-construcao').status_code == 404
    assert client.get('/dash/backlog/api/debug').status_code == 404


def test_config_preserves_special_password(monkeypatch):
    monkeypatch.setattr(Config, 'DB_PASSWORD', 'p@ss:/?#%')
    assert make_url(Config.db_url()).password == 'p@ss:/?#%'


def test_cache_isolation_expiration_and_columns(monkeypatch):
    db.clear_cache()
    engine=MagicMock()
    monkeypatch.setattr(db, 'get_engine', lambda: engine)
    source=pd.DataFrame({'SAFRA':['1 MES'], 'ANL_MOTIVO_REAGENDA':['CLIENTE']})
    calls=[]
    def read(sql, eng):
        calls.append(sql)
        return source.copy()
    monkeypatch.setattr(pd, 'read_sql', read)
    first=db.load_table('safra_enriquecida', ['SAFRA'])
    first['SAFRA']='ALTERADO'
    second=db.load_table('safra_enriquecida')
    assert second.iloc[0]['SAFRA']=='1 MES'
    assert 'ANL_MOTIVO_REAGENDA' in calls[1]
    assert len(calls)==2
    db._CACHE['safra_enriquecida']['clock']=-100000
    db.load_table('safra_enriquecida')
    assert len(calls)==4
    assert engine.dispose.call_count==2


def test_database_failure_is_not_empty_success(monkeypatch):
    db.clear_cache()
    engine=MagicMock()
    monkeypatch.setattr(db, 'get_engine', lambda:engine)
    monkeypatch.setattr(pd,'read_sql',MagicMock(side_effect=RuntimeError('private password')))
    with pytest.raises(db.DatabaseUnavailable): db.load_table('safra_final')
    engine.dispose.assert_called_once()
    assert 'safra_final' not in db._CACHE
    with pytest.raises(ValueError): db.load_table('table; DROP TABLE x')


@pytest.mark.parametrize('panel,endpoint', [(executivo,'/dash/executivo/api/data'), (log,'/dash/log/api/data'), (backlog,'/dash/backlog/api/refresh'), (parceiras,'/dash/parceiras/api/refresh')])
def test_panels_nullable_categories(app, monkeypatch, frame, panel, endpoint):
    source=frame.copy()
    for col in source: source[col]=source[col].astype('category')
    monkeypatch.setattr(panel,'load_table',lambda *a,**k:source.copy())
    response=app.test_client().get(endpoint)
    assert response.status_code==200, response.text
    payload=response.get_json()
    assert not payload.get('error'), payload
    assert 'bdata' not in response.text
    assert 'Erro G' not in response.text


def test_log_does_not_mutate_shared_frame(monkeypatch, frame):
    original=frame.copy(deep=True)
    monkeypatch.setattr(log,'load_table',lambda *a,**k:frame.copy())
    prepared=log.prepare_df()
    pd.testing.assert_frame_equal(frame,original)
    assert log.montar_kpis(prepared)['com_log']==1
    assert sum(log.chart_tipo_log(prepared)['series']['COM LOG'])==1


def test_backlog_small_sample_has_aging(monkeypatch,frame):
    monkeypatch.setattr(backlog,'load_table',lambda *a,**k:frame.copy())
    assert backlog.get_df()['FAIXA_AGING'].tolist()[:2]==['0-7d','16-30d']


def test_recovery_numeric_and_text_flags():
    for values in [[0.0,1.0,None], ['RECUPERADO','PENDENTE',None]]:
        result=executivo.prepare_df(pd.DataFrame({'PENDENCIA':values}))
        assert result['_RECUP'].sum()==1


def test_quebra_missing_calendar_and_chronology():
    frame=quebra._prepare_df(pd.DataFrame({'DT_AGENDA':['2026-09-02','2026-09-01',None], 'NR_CONTRATO':['a','b','c'], 'NM_TIPO_TRATAMENTO':[quebra.QUEBRA_VALUE]*3}))
    assert frame['MES'].tolist()==['09','09','']
    assert frame['DIA'].tolist()==['02','01','']
    chart=quebra._series_payload(frame.iloc[:2],frame,'DIA','Dias','quantidade',sort_desc=False)
    assert chart['labels']==['01','02']


def monthly(**extra):
    row=dict(ano=2026,mes=9,nivel='CIDADE',uf='AM',cidade='MANAUS',safra='1 MES',ds_tipo_desconexao='INAD',desc_total=100,rec_total=50,meta_percentual=60,meta_qtd=60)
    return row | extra


def test_safra_hierarchy_and_weighted_percentages():
    rows=[monthly(),monthly(cidade='BELEM',uf='PA',desc_total=900,rec_total=90,meta_qtd=540),monthly(nivel='RNO',cidade=None,desc_total=1000,rec_total=140,meta_qtd=600)]
    k=safra.montar_kpis(rows,[])
    assert (k['desc'],k['rec'],k['pct'],k['meta'])==(1000,140,14,60)
    assert k['gap_vol']==-460
    assert safra.montar_comparativo(rows)==[{'safra':'1 MES','pct':14}]
    assert safra.montar_tipos(rows)==[{'tipo':'INAD','pct':14}]


def test_safra_matrix_aggregates_periods():
    rows=[monthly(),monthly(mes=8,desc_total=900,rec_total=90,meta_qtd=540)]
    result=safra.montar_matriz(rows)[0]
    assert result['inad_desc']==1000
    assert result['inad_rec']==140
    assert result['inad_pct']==14
    assert safra.montar_ranking(rows)[0]['pct']==14


def test_safra_daily_snapshot_and_need():
    rows=[monthly(dia=1,desc_total_mes=100,rec_acumulado=20,necessario_por_dia=3),monthly(dia=2,desc_total_mes=100,rec_acumulado=30,necessario_por_dia=2),monthly(cidade='BELEM',dia=2,desc_total_mes=100,rec_acumulado=40,necessario_por_dia=1)]
    snapshot=safra._monthly_snapshot(rows)
    k=safra.montar_kpis(snapshot,rows)
    assert k['rec']==70
    assert k['desc']==200
    assert k['necessario_dia']==3


def test_safra_query_parameterization():
    where,params=safra.build_where({'cidade':"x' OR 1=1 --",'dia':'1,2'},'safra_resumo_diario')
    assert "OR 1=1" not in where
    assert params==["x' OR 1=1 --",'1','2']


def test_safra_error_status_and_diagnostic(app,monkeypatch):
    monkeypatch.setattr(safra,'query',MagicMock(side_effect=RuntimeError('password=secret')))
    for endpoint in ['data','options','diagnostico']:
        response=app.test_client().get('/dash/safra/api/'+endpoint)
        assert response.status_code==503
        assert 'secret' not in response.text
        assert 'Traceback' not in response.text


def test_retirada_requires_universe_column(monkeypatch):
    monkeypatch.setattr(retirada,'_resolve_columns',lambda:{'NM_CIDADE':'NM_CIDADE','TEM_TOA':None})
    with pytest.raises(RuntimeError): retirada._build_select_sql()


def test_retirada_login_does_not_swallow_handler_error(app):
    calls=[]
    @retirada.safe_login_required
    def broken():
        calls.append(1)
        raise AttributeError('bug')
    with app.test_request_context():
        with pytest.raises(AttributeError): broken()
    assert len(calls)==1


def test_safra_empty_api(app,monkeypatch):
    monkeypatch.setattr(safra,'query',lambda *a,**k:[])
    response=app.test_client().get('/dash/safra/api/data')
    assert response.status_code==200
    assert response.get_json()['kpis']['desc']==0


def test_retirada_payload(app,monkeypatch):
    frame=pd.DataFrame({'PERFORMANCE':['CONCLUIDA','FALHA','EM ABERTO'], 'NM_CIDADE':['A','A','B'], 'SAFRA':['1 MES']*3, 'DS_TIPO_DESCONEXAO':['INAD']*3})
    monkeypatch.setattr(retirada,'carregar_dados',lambda:frame)
    response=app.test_client().get('/dash/retirada/api/dados')
    assert response.status_code==200
    assert response.get_json()['kpis']['qtd_concluida']==1


def test_quebra_payload(app,monkeypatch):
    frame=quebra._prepare_df(pd.DataFrame({'NR_CONTRATO':['1','2'], 'NM_TIPO_TRATAMENTO':[quebra.QUEBRA_VALUE,quebra.SEM_QUEBRA_VALUE]}))
    monkeypatch.setattr(quebra,'_load_df',lambda **k:frame)
    response=app.test_client().get('/dash/quebra/api/refresh')
    assert response.status_code==200
    assert response.get_json()['kpis']['taxa_quebra']==50


def test_all_template_scripts_compile(app,monkeypatch,tmp_path):
    node=shutil.which('node')
    if not node:
        pytest.skip('Node.js é necessário para validar JavaScript')
    monkeypatch.setattr(executivo,'get_options',lambda:{})
    with app.test_request_context():
        for name in app.jinja_env.list_templates():
            if name in {'home.html','area.html'}:
                continue
            html=app.jinja_env.get_template(name).render(opts={})
            for i,code in enumerate(re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S)):
                if not code.strip(): continue
                script=tmp_path/'check.js'
                script.write_text(code,encoding='utf-8')
                result=subprocess.run([node,'--check',str(script)],capture_output=True,text=True)
                assert result.returncode==0, (name,i,result.stderr)


@pytest.mark.parametrize('panel,endpoint',[(log,'/dash/log/api/data'),(backlog,'/dash/backlog/api/refresh'),(parceiras,'/dash/parceiras/api/refresh')])
def test_empty_tables(app,monkeypatch,panel,endpoint):
    monkeypatch.setattr(panel,'load_table',lambda *a,**k:pd.DataFrame())
    response=app.test_client().get(endpoint)
    assert response.status_code==200,response.text


@pytest.mark.parametrize('panel,endpoint',[(executivo,'/dash/executivo/api/data?safra=INEXISTENTE'),(log,'/dash/log/api/data?SAFRA=INEXISTENTE'),(backlog,'/dash/backlog/api/refresh?SAFRA=INEXISTENTE'),(parceiras,'/dash/parceiras/api/refresh?SAFRA=INEXISTENTE')])
def test_filters_without_matches(app,monkeypatch,frame,panel,endpoint):
    monkeypatch.setattr(panel,'load_table',lambda *a,**k:frame.copy())
    response=app.test_client().get(endpoint)
    assert response.status_code==200,response.text
    payload=response.get_json()
    assert payload.get('empty') or payload['kpis']['total']==0


def test_safra_day_filter_uses_daily_accumulation(app,monkeypatch):
    def query(sql,params=None):
        if 'DISTINCT' in sql:return []
        if 'safra_resumo_diario' in sql:
            return [monthly(dia=2,desc_total_mes=100,rec_acumulado=20)]
        return [monthly()]
    monkeypatch.setattr(safra,'query',query)
    response=app.test_client().get('/dash/safra/api/data?dia=2')
    assert response.get_json()['kpis']['rec']==20
