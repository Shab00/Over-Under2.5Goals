| Feature                  | Type         | Pre-Match? | Description                                                           |
|--------------------------|--------------|------------|-----------------------------------------------------------------------|
| Date                     | Date         | Yes        | Match date                                                            |
| FTHG                     | Numeric      | No         | Full time home goals (outcome/leakage)                                |
| FTAG                     | Numeric      | No         | Full time away goals (outcome/leakage)                                |
| HTHG                     | Numeric      | No         | Half time home goals (outcome/leakage)                                |
| HTAG                     | Numeric      | No         | Half time away goals (outcome/leakage)                                |
| Referee                  | Categorical  | Yes        | Name of referee                                                       |
| HS                       | Numeric      | No         | Home team shots (usually post-match)                                  |
| AS                       | Numeric      | No         | Away team shots (post-match)                                          |
| HST                      | Numeric      | No         | Home shots on target (post-match)                                     |
| AST                      | Numeric      | No         | Away shots on target (post-match)                                     |
| HC                       | Numeric      | No         | Home corners (post-match)                                             |
| AC                       | Numeric      | No         | Away corners (post-match)                                             |
| HF                       | Numeric      | No         | Home fouls (post-match)                                               |
| AF                       | Numeric      | No         | Away fouls (post-match)                                               |
| HY                       | Numeric      | No         | Home yellow cards (post-match)                                        |
| AY                       | Numeric      | No         | Away yellow cards (post-match)                                        |
| HR                       | Numeric      | No         | Home red cards (post-match)                                           |
| AR                       | Numeric      | No         | Away red cards (post-match)                                           |
| IWH                      | Numeric      | Yes        | Bookmaker (Interwetten) odds home win (pre-match)                     |
| IWD                      | Numeric      | Yes        | Bookmaker odds draw (pre-match)                                       |
| IWA                      | Numeric      | Yes        | Bookmaker odds away win (pre-match)                                   |
| WHH                      | Numeric      | Yes        | Bookmaker (William Hill) odds home win (pre-match)                    |
| WHD                      | Numeric      | Yes        | Bookmaker odds draw (pre-match)                                       |
| WHA                      | Numeric      | Yes        | Bookmaker odds away win (pre-match)                                   |
| Year                     | Numeric      | Yes        | Year of match                                                         |
| Month                    | Numeric      | Yes        | Month of match                                                        |
| DayOfWeek                | Numeric      | Yes        | Day of week (0=Monday, etc.)                                          |
| TotalGoals               | Numeric      | No         | Total goals (outcome/leakage)                                         |
| GoalsOver2_5             | Numeric      | No         | Target: 1 if over 2.5 goals, else 0 (leakage)                         |
| HomeTeam_mean_FTHG       | Numeric      | Yes        | Average home team goals (should be pre-match form, check how computed) |
| AwayTeam_mean_FTAG       | Numeric      | Yes        | Average away team goals (should be pre-match form, check how computed) |
| HomeTeam_*               | One-hot      | Yes        | Home team identity (one-hot encoded)                                  |
| AwayTeam_*               | One-hot      | Yes        | Away team identity (one-hot encoded)                                  |
| FTR_A                    | One-hot      | No         | Full-time result: away win (outcome/leakage)                          |
| FTR_D                    | One-hot      | No         | Full-time result: draw (outcome/leakage)                              |
| FTR_H                    | One-hot      | No         | Full-time result: home win (outcome/leakage)                          |
| HTR_A                    | One-hot      | No         | Half-time result: away (outcome/leakage)                              |
| HTR_D                    | One-hot      | No         | Half-time result: draw (outcome/leakage)                              |
| HTR_H                    | One-hot      | No         | Half-time result: home (outcome/leakage)                              |
