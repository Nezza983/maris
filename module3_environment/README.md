# Module 3 — Wind & Ocean Current Data Pipeline

**Owner:** Najma | **Project:** SLICKTRACE (SIH Hackathon)

## What this module does

Given a spill location and time, this module produces the wind and ocean current
values at that point/time, so Module 4 can run OpenDrift to simulate where the
oil came from and where it is going.

**You are a data supply module.** Your entire job is producing one correct,
correctly-formatted file: .

## Output contract (what Module 4 expects from you)



Units: **m/s**. Sign convention: positive = eastward (u) / northward (v).

## Accounts needed

| Account | URL | Notes |
|---|---|---|
| Copernicus Marine (CMEMS) | https://data.marine.copernicus.eu/register | Free. Grants access to the entire catalog immediately. |
| Climate Data Store (CDS) | https://cds.climate.copernicus.eu | Free. Requires accepting ERA5 Terms of Use before API calls work. |

## How to run (Google Colab)

1. Upload  to Colab
2. Add Colab Secrets: , , 
3. Run all cells top to bottom
4. Cell 7 produces 
5. Cell 8 runs a sanity check

## How to run (local Python)



Or with explicit coordinates:



Use  to skip APIs and generate placeholder data:



## Inter-module integration

Module 3 reads its input from  (written by Module 1).
The expected format:



If this file is not found, the pipeline falls back to built-in demo values.

## Data sources

| Variable | Source | Dataset ID |
|---|---|---|
| Ocean currents (uo, vo) | CMEMS |  |
| Wind at 10m (u10, v10) | ERA5 via CDS |  |

## Troubleshooting

| Problem | Fix |
|---|---|
| CDS call fails: "required licences not accepted" | Accept ERA5 Terms of Use on the CDS website |
| CMEMS auth error | Check CMEMS_USER is your email, not a display name |
| Interpolated values are NaN | Point may be over land or outside the time window |
| Values look absurd (hundreds of m/s) | Check surface layer (depth=0) is used |
| Colab session disconnects | Re-run from the credentials cell |

## Files

| File | Description |
|---|---|
|  | CMEMS ocean current fetcher |
|  | ERA5 wind data fetcher |
|  | Main CLI entry point |
|  | Colab notebook (same logic, interactive) |
|  | This file |
