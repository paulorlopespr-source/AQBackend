# AQ Backend v0.1.0

Backend seguro do **Assistente Quantitativo (AQ)**.

## Arquitetura

```text
Android AQ
   ↓ HTTPS + JWT
AQ Backend (FastAPI)
   ├── PostgreSQL
   ├── Gestão de banca
   ├── Bilhetes e pernas
   ├── Regras de liquidação
   ├── Motor de risco
   ├── API esportiva
   ├── Sincronização
   └── Camada de IA
        ↓
API-Football / futura IA
```

As chaves `SPORTS_API_KEY` e `OPENAI_API_KEY` ficam apenas nas variáveis de ambiente do backend.
Elas **não são devolvidas em nenhum endpoint** e não precisam ficar no APK.

## O que já está implementado

- Login e JWT.
- Banca principal:
  - saldo;
  - meta;
  - stake/unidade;
  - stake máxima;
  - stop loss diário e mensal;
  - ROI e lucro.
- Métodos:
  - CRUD;
  - win rate;
  - ROI;
  - lucro/prejuízo;
  - odd média;
  - drawdown.
- Bilhetes:
  - registro;
  - reserva da stake;
  - probabilidade quantitativa;
  - risco baixo/moderado/alto;
  - múltiplas;
  - liquidação.
- Regras automáticas:
  - resultado final;
  - ambas marcam;
  - Over/Under gols;
  - Over/Under escanteios;
  - Over/Under cartões;
  - totais asiáticos `.25/.75`;
  - push;
  - meia vitória;
  - meia perda.
- API esportiva:
  - jogos por data;
  - últimos 5 jogos;
  - placar final;
  - estatísticas de fixture.
- Sincronização:
  - manual por bilhete;
  - endpoint interno protegido para cron;
  - loop opcional para ambiente simples.
- IA:
  - segredo preparado no backend;
  - adapter separado;
  - ainda sem chamada remota nesta versão.

## Segurança

### Nunca coloque no Android

- `SPORTS_API_KEY`
- `OPENAI_API_KEY`
- `JWT_SECRET`
- `INTERNAL_CRON_TOKEN`

O Android recebe apenas o JWT após autenticação.

### Produção

Para produção, use:
- HTTPS;
- PostgreSQL;
- senhas reais e usuários no banco;
- rotação de secrets;
- logs sem secrets;
- `SYNC_MODE=cron`;
- uma chamada periódica protegida para `/api/v1/internal/sync`.

O modo `loop` é útil no desenvolvimento, mas em produção com múltiplas réplicas poderia executar a sincronização mais de uma vez.

## Executar localmente

### 1. Criar `.env`

Copie:

```bash
cp .env.example .env
```

Edite as variáveis.

### 2. Subir PostgreSQL + API

```bash
docker compose up --build
```

API:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

Health:

```text
GET /health
```

## Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "sua-senha"
}
```

Resposta:

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

Depois envie:

```text
Authorization: Bearer <token>
```

## Criar banca

```http
PUT /api/v1/bankroll
```

```json
{
  "name": "Banca Principal",
  "initial_value": 1000,
  "current_value": 1000,
  "target_value": 2000,
  "unit_percent": 1,
  "max_stake_percent": 2.5,
  "daily_loss_limit_percent": 5,
  "monthly_loss_limit_percent": 15
}
```

## Criar bilhete

```http
POST /api/v1/tickets
```

```json
{
  "stake": 20,
  "legs": [
    {
      "fixture_id": 123456,
      "match_label": "Time A x Time B",
      "market_id": "goals_2.5",
      "market_label": "Total de Gols",
      "selection_side": "UNDER",
      "line": 2.5,
      "odd": 1.65,
      "estimated_probability": 82
    }
  ]
}
```

No registro:
- a stake é retirada do saldo disponível;
- o bilhete é salvo;
- o backend calcula a probabilidade final;
- a banca será atualizada na liquidação.

## Sincronização automática

Recomendado em produção:

```http
POST /api/v1/internal/sync
X-Cron-Token: <INTERNAL_CRON_TOKEN>
```

Configure seu serviço de cron para chamar esse endpoint periodicamente.

## Próxima etapa

1. Publicar backend no Railway.
2. Criar PostgreSQL no Railway.
3. Adicionar secrets nas Variables.
4. Testar `/health`.
5. Configurar `SPORTS_API_KEY`.
6. Ligar o Android ao backend.
7. Substituir dados locais de jogos/bilhetes por API.
8. Implementar usuário real e refresh token.
9. Habilitar interpretação por IA.
