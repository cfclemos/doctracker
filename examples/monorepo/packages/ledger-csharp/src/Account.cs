namespace Acme.Ledger;

/// <summary>An account and its balance.</summary>
public class Account
{
    /// <summary>The balance, in cents.</summary>
    public long Balance { get; private set; }

    /// <summary>Put money into the account.</summary>
    public void Deposit(long cents) => Balance += cents;

    /// <summary>Take money out, when there is enough.</summary>
    public bool Withdraw(long cents)
    {
        if (cents > Balance) return false;
        Balance -= cents;
        return true;
    }
}
