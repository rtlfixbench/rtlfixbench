# RTLFixBench  

RTLFixBench is a benchmark suite designed to evaluate the performance of RTL debugging and repair tools across varying levels of complexity.

---

## Installation  
To set up RTLFixBench, run:  
```bash
./install.sh
```

---

## Usage  

### Running Benchmarks  
Execute the test suite with your preferred framework:  
```bash
./run.sh -t [framework_name]
```

**Examples:**  
```bash
# Run benchmarks with MEIC
./run.sh -t meic

# Run benchmarks with RTL-Repair
./run.sh -t rtlrepair
```

---

## Configuration  
Framework-specific settings can be modified in their respective configuration files:  

| Framework    | Configuration Path                          |
|--------------|---------------------------------------------|
| CirFix       | `resources/configs/cirfix/settings.json`    |
| RTL-Repair   | `resources/configs/rtlrepair/settings.json` |
| MEIC         | `resources/configs/meic/settings.json`      |

---

## Supported Frameworks  
RTLFixBench currently supports these state-of-the-art repair tools:  

| Framework     | Approach               | Publication | Code |
|--------------|------------------------|-------------|------|
| CirFix     | Fitness-guided repair  | ASPLOS 2022 | [GitHub](https://github.com/hammad-a/verilog_repair) |
| RTL-Repair | Symbolic execution     | ASPLOS 2024 | [GitHub](https://github.com/ekiwi/rtl-repair) |
| MEIC       | LLM-driven repair      | ICCAD 2024  | [GitHub](https://github.com/SEU-ACAL/reproduce-MEIC-ICCAD) |

---

## License  
This project is licensed under the **[MIT License](LICENSE)**.

---

## References  
1. **[CirFix]** H. Ahmad et al., "CirFix: Automatically Repairing Defects in Hardware Design Code," *ASPLOS 2022*.  
   [DOI:10.1145/3503222.3507763](https://doi.org/10.1145/3503222.3507763)  

2. **[RTL-Repair]** K. Laeufer et al., "RTL-Repair: Fast Symbolic Repair of Hardware Design Code," *ASPLOS 2024*.  
   [DOI:10.1145/3620666.3651346](https://doi.org/10.1145/3620666.3651346)  

3. **[MEIC]** K. Xu et al., "MEIC: Re-thinking RTL Debug Automation using LLMs," *ICCAD 2024*.  
   [DOI:10.48550/arXiv.2405.06840](https://doi.org/10.48550/arXiv.2405.06840)  

---
