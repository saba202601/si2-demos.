/* SI² Canonical Master: create the database (SQL Server 2017 or later, Express is fine).
   Run in SSMS or with the installer: python install_si2_canonical.py                                  */
IF DB_ID(N'SI2Canonical') IS NULL
    CREATE DATABASE SI2Canonical;
GO
ALTER DATABASE SI2Canonical SET RECOVERY SIMPLE;
GO
