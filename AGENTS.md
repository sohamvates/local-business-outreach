# AGENTS.md

Leia este arquivo antes de qualquer mudança futura no projeto.

## Regras obrigatórias

- Sempre ler `AGENTS.md` antes de mexer.
- Sempre revisar o mapa atual do sistema antes de editar.
- Nunca assumir que algo está ausente sem verificar no código e na UI.
- Nunca refazer módulo funcional.
- Nunca trocar arquitetura.
- Nunca adicionar login, scheduler, Docker, Redis, Celery ou stack nova sem pedido explícito.
- O sistema é local, single-user e manual por decisão do dono.
- O fluxo de envio é manual: scrape -> gerar email -> revisar -> aprovar/rejeitar -> enviar.
- Não quebrar Gmail/custom SMTP.
- Não quebrar Google Maps.
- Não quebrar Google Sheets.
- Não quebrar CRM.
- Não inventar email de empresa.
- Não duplicar leads por domain, email, place_id ou email já enviado.
- Não expor secrets.
- Não mostrar API keys, senhas, tokens ou service account.

## Antes de editar

Sempre informar:

1. o que será alterado;
2. por quê;
3. arquivos impactados;
4. risco;
5. validação.

## Estratégia de mudança

- Fazer alterações pequenas e reversíveis.
- Preferir ajuste cirúrgico sobre refactor amplo.
- Validar o fluxo existente antes de concluir que algo está quebrado.
- Não alterar backend, frontend, banco, rotas ou UI fora do escopo pedido.

## Depois de editar

Validar e reportar apenas:

1. arquivos alterados;
2. o que mudou;
3. como testar;
4. resultado.
