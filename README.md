# Bank_API
📌 Project Summary

This project is a Banking API built with FastAPI, providing essential banking operations such as account creation, authentication, deposits, withdrawals, fund transfers, and transaction history tracking.
It uses in-memory data storage for simplicity and demonstration purposes, making it ideal for learning FastAPI and REST API design.

The API automatically seeds two sample accounts (alice and bob) at startup and includes proper request/response models using Pydantic.
Each action generates a transaction record, including transaction ID, timestamp, type (deposit, withdraw, transfer), and linked account information for transfers.
