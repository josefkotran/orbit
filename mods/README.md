# Mody Orbitu pro Claude Code

Dva [mody](https://code.claude.com/docs/en/plugins/mods/overview) (doplňky, které běží přímo v Claude Code). Potřebují
Claude Code 2.1.287 nebo novější. Fungují v terminálu i na kartě Code v aplikaci Claude.

| Mod | Co dělá |
|---|---|
| `orbit-mozek` | `/mozek` otevře vedle konverzace panel „Mozek“. Ukazuje, o čem Claude právě přemýšlí, co píše, které nástroje běží a jak dlouho, co dělají podagenti, „mozkovou vlnu“ (kolik napsal v každém kroku) a kontext rozdělený podle kategorií jako `/context`, s limity. Limity (5 h a týden) po každém tahu předá i panelu Orbitu: zapíše je do jeho datové složky v počítači, bez jediného dotazu na server. Nic se nikam neposílá. |
| `orbit-ukoly` | V relaci, kterou Orbit založil z úkolu v Poznámkách, je nad promptem řádek s úkolem a tlačítky **Poznámka** a **Hotovo**. Claude ví, na čem pracuje, a dostane dva nástroje: zapsat poznámku k úkolu a úkol dokončit. Orbit pak úkol přesune do Hotovo a ozve se bublinou. `/ukol` vypíše aktivní úkoly a relaci připojí k jednomu (`/ukol 2`), `/ukol odpojit` ji odpojí. |

## Instalace

V Claude Code (v terminálu):

```
/plugin install orbit-mozek --marketplace josefkotran/orbit
/plugin install orbit-ukoly --marketplace josefkotran/orbit
```

Nejdřív `y` (přidat marketplace), pak rozsah (Enter = pro tebe ve všech projektech). Ze složky s Orbitem
(vývoj): `claude plugin marketplace add <složka s Orbitem>` a `claude plugin install orbit-mozek@orbit`. Claude Code
si mod zkopíruje k sobě (`~/.claude/plugins/cache/orbit/…`), takže po úpravě zvedni `version` v `plugin.json`
a spusť `claude plugin marketplace update orbit` a `claude plugin update orbit-mozek@orbit`; relace ho načtou po
restartu.

## Jak `orbit-ukoly` mluví s Orbitem

- Orbit zakládá relaci úkolu s proměnnými `ORBIT_TASK_ID` (číslo úkolu) a `ORBIT_TASK_DATA` (datová složka Orbitu).
  Relace bez nich (otevřená ručně) úkol nemá, dokud ji uživatel nepřipojí `/ukol <číslo>`; připojení si mod pamatuje
  i po obnovení relace.
- Mod úkol jen čte z `tasks.json`. Poznámky a „hotovo“ zapisuje jako malé soubory JSON do `<data>/tasks/inbox/`
  (`{"task", "action": "note" | "done", "text", "from": "claude" | "user", "at"}`); Orbit je do 3 s převezme
  (`tasks.read_inbox`), soubor smaže a změní úkol. `tasks.json` tak zapisuje jen Orbit.
- Poznámky od Clauda mají v Poznámkách na začátku „Claude:“.

## Vývoj

Každý mod jsou tři soubory (`.claude-plugin/plugin.json`, `hooks/hooks.json`, `hooks/register.tsx`), `types/index.d.ts`
s hodnotami, ze kterých se kreslí, a testy v `tests/`. Kontrola:

```
claude plugin validate mods/orbit-mozek
claude plugin test mods/orbit-mozek
```

Typy API si Claude Code zapisuje do `.claude-plugin/types/` (v gitu nejsou); s nimi i `tsc -p mods/orbit-mozek`.
API modů je zatím v ranném přístupu a mezi verzemi Claude Code se může změnit.
