from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional
from datetime import datetime
import uuid

app = FastAPI(title="Bank API")

# In-memory databases
# For simplicity, authentication is not fully implemented (e.g., hashing passwords, real tokens)
# Accounts are stored by account_name for easy access
accounts_db: Dict[str, "Account"] = {}
transactions_db: List["TransactionRecord"] = []

# Seed some initial data
class InitialAccount(BaseModel):
    name: str
    pin: str
    initial_balance: float

initial_accounts_data = [
    InitialAccount(name="alice", pin="1234", initial_balance=1000.0),
    InitialAccount(name="bob", pin="5678", initial_balance=500.0)
]

class AuthRequest(BaseModel):
    name: str
    pin: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class AccountCreate(BaseModel):
    name: str
    pin: str = Field(..., min_length=4, max_length=4, regex="^[0-9]{4}$", description="4-digit PIN")
    initial_balance: float = Field(default=0.0, ge=0.0)

class Account(BaseModel):
    name: str
    pin: str  # In a real app, this would be hashed
    balance: float
    created_at: datetime = Field(default_factory=datetime.now)

class AccountResponse(BaseModel):
    name: str
    balance: float
    created_at: datetime

class DepositRequest(BaseModel):
    account_name: str
    amount: float = Field(..., gt=0)

class WithdrawRequest(BaseModel):
    account_name: str
    amount: float = Field(..., gt=0)

class TransferRequest(BaseModel):
    sender_name: str
    sender_pin: str
    recipient_name: str
    amount: float = Field(..., gt=0)

class TransactionRecord(BaseModel):
    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account_name: str
    type: Literal["deposit", "withdraw", "transfer_out", "transfer_in"]
    amount: float
    timestamp: datetime = Field(default_factory=datetime.now)
    # For transfers, store linked account
    linked_account: Optional[str] = None
    # For transfers, store status
    status: Literal["completed", "pending", "failed"] = "completed"

# Populate initial accounts
for acc_data in initial_accounts_data:
    if acc_data.name not in accounts_db:
        accounts_db[acc_data.name] = Account(
            name=acc_data.name,
            pin=acc_data.pin,
            balance=acc_data.initial_balance
        )

# --- Endpoints ---

@app.post("/auth", response_model=AuthResponse, summary="Authenticate user and get a token")
async def authenticate_user(credentials: AuthRequest):
    account = accounts_db.get(credentials.name)
    if not account or account.pin != credentials.pin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # For a real application, you'd generate a JWT or similar token
    token = f"{credentials.name}-{str(uuid.uuid4())}-token"
    return AuthResponse(access_token=token)

@app.post("/accounts", response_model=AccountResponse, summary="Create a new bank account")
async def create_account(account_data: AccountCreate):
    if account_data.name in accounts_db:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account with this name already exists")
    
    new_account = Account(
        name=account_data.name,
        pin=account_data.pin,
        balance=account_data.initial_balance
    )
    accounts_db[new_account.name] = new_account
    return AccountResponse(
        name=new_account.name,
        balance=new_account.balance,
        created_at=new_account.created_at
    )

@app.get("/accounts/{account_name}", response_model=AccountResponse, summary="Get account details")
async def get_account(account_name: str):
    account = accounts_db.get(account_name)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return AccountResponse(
        name=account.name,
        balance=account.balance,
        created_at=account.created_at
    )

@app.post("/transactions/deposit", summary="Deposit funds into an account")
async def deposit_funds(deposit: DepositRequest):
    account = accounts_db.get(deposit.account_name)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    account.balance += deposit.amount
    
    transaction = TransactionRecord(
        account_name=account.name,
        type="deposit",
        amount=deposit.amount
    )
    transactions_db.append(transaction)
    
    return {"message": f"Successfully deposited {deposit.amount} into {account.name}", "new_balance": account.balance}

@app.post("/transactions/withdraw", summary="Withdraw funds from an account")
async def withdraw_funds(withdraw: WithdrawRequest):
    account = accounts_db.get(withdraw.account_name)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if account.balance < withdraw.amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    account.balance -= withdraw.amount
    
    transaction = TransactionRecord(
        account_name=account.name,
        type="withdraw",
        amount=withdraw.amount
    )
    transactions_db.append(transaction)
    
    return {"message": f"Successfully withdrew {withdraw.amount} from {account.name}", "new_balance": account.balance}

@app.post("/transactions/transfer", summary="Transfer funds between accounts")
async def transfer_funds(transfer: TransferRequest):
    sender_account = accounts_db.get(transfer.sender_name)
    recipient_account = accounts_db.get(transfer.recipient_name)

    if not sender_account or sender_account.pin != transfer.sender_pin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid sender credentials")
    
    if not recipient_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient account not found")

    if sender_account.balance < transfer.amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    # Perform the transfer
    sender_account.balance -= transfer.amount
    recipient_account.balance += transfer.amount

    # Record sender's transaction
    transactions_db.append(TransactionRecord(
        account_name=sender_account.name,
        type="transfer_out",
        amount=transfer.amount,
        linked_account=recipient_account.name
    ))
    # Record recipient's transaction
    transactions_db.append(TransactionRecord(
        account_name=recipient_account.name,
        type="transfer_in",
        amount=transfer.amount,
        linked_account=sender_account.name
    ))

    return {
        "message": "Transfer successful",
        "sender_new_balance": sender_account.balance,
        "recipient_new_balance": recipient_account.balance
    }

@app.get("/accounts/{account_name}/transactions", response_model=List[TransactionRecord], summary="Get transaction history for an account")
async def get_account_transactions(account_name: str):
    if account_name not in accounts_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    
    account_transactions = [
        t for t in transactions_db if t.account_name == account_name or t.linked_account == account_name
    ]
    # Optionally, filter for only transactions where account_name is the primary participant
    # account_transactions = [t for t in transactions_db if t.account_name == account_name]
    return account_transactions