"""Configuração das 8 áreas operacionais e seus setores."""

AREAS = [
    {
        "slug": "adm",
        "nome": "ADM",
        "descricao": "Administrativo · desconexão e segurança operacional",
        "icone": "fa-clipboard-list",
        "cor": "red",
        "ativo": True,
        "meta": "2 setores",
        "setores": [
            {
                "slug": "desconexao",
                "nome": "Desconexão",
                "descricao": "Gestão e indicadores do processo de desconexão",
                "icone": "fa-plug-circle-xmark",
                "cor": "red",
                "ativo": True,
                "meta": "6 dashboards",
            },
            {
                "slug": "seguranca",
                "nome": "Segurança",
                "descricao": "Gestão de segurança patrimonial e operacional",
                "icone": "fa-shield-halved",
                "cor": "dark",
                "ativo": False,
                "meta": "",
            },
        ],
    },
    {
        "slug": "omr",
        "nome": "OMR",
        "descricao": "Operação e Monitoramento de Rede",
        "icone": "fa-satellite-dish",
        "cor": "purple",
        "ativo": False,
        "meta": "",
        "setores": [],
    },
    {
        "slug": "infra",
        "nome": "INFRA",
        "descricao": "Infraestrutura de rede e datacenter",
        "icone": "fa-network-wired",
        "cor": "blue",
        "ativo": False,
        "meta": "",
        "setores": [],
    },
    {
        "slug": "implantacao",
        "nome": "Implantação",
        "descricao": "Projetos e implantações de rede",
        "icone": "fa-screwdriver-wrench",
        "cor": "orange",
        "ativo": False,
        "meta": "",
        "setores": [],
    },
    {
        "slug": "rede-externa",
        "nome": "Rede Externa",
        "descricao": "Planta externa e expansão",
        "icone": "fa-tower-broadcast",
        "cor": "green",
        "ativo": False,
        "meta": "",
        "setores": [],
    },
    {
        "slug": "residencial",
        "nome": "Residencial",
        "descricao": "Clientes residenciais",
        "icone": "fa-house",
        "cor": "pink",
        "ativo": False,
        "meta": "",
        "setores": [],
    },
    {
        "slug": "empresarial",
        "nome": "Empresarial",
        "descricao": "Clientes corporativos",
        "icone": "fa-building",
        "cor": "dark",
        "ativo": False,
        "meta": "",
        "setores": [],
    },
    {
        "slug": "backbone",
        "nome": "Backbone",
        "descricao": "Espinha dorsal da rede",
        "icone": "fa-diagram-project",
        "cor": "teal",
        "ativo": False,
        "meta": "",
        "setores": [],
    },
]


def get_area(slug):
    """Retorna a área pelo slug ou None."""
    for a in AREAS:
        if a["slug"] == slug:
            return a
    return None


def get_setor(area, slug):
    """Retorna o setor pelo slug ou None."""
    for s in area.get("setores", []):
        if s["slug"] == slug:
            return s
    return None
