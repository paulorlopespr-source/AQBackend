from app.models.entities import Bankroll, BetTicket, TicketStatus


def reserve_stake(bankroll: Bankroll, stake: float) -> None:
    if stake <= 0:
        raise ValueError("Stake inválida")
    if bankroll.current_value < stake:
        raise ValueError("Saldo insuficiente na banca")
    bankroll.current_value -= stake


def apply_ticket_result(bankroll: Bankroll, ticket: BetTicket) -> None:
    if ticket.bankroll_applied:
        return

    if ticket.status not in {
        TicketStatus.GREEN.value,
        TicketStatus.RED.value,
        TicketStatus.REFUND.value,
        TicketStatus.PARTIAL.value,
    }:
        return

    credit = ticket.settled_return
    bankroll.current_value += credit

    profit = credit - ticket.stake
    bankroll.monthly_profit += profit
    bankroll.entries += 1

    base = bankroll.initial_value if bankroll.initial_value > 0 else 1.0
    bankroll.roi = (bankroll.monthly_profit / base) * 100
    ticket.bankroll_applied = True
