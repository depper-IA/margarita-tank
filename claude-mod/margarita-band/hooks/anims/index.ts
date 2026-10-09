import type { AnimName } from '../../types'
import { alert } from './alert'
import { beacon } from './beacon'
import { building } from './building'
import { conducting } from './conducting'
import { confused } from './confused'
import { debuggerAnim } from './debugger'
import { dizzy } from './dizzy'
import { happy } from './happy'
import { hatMishap } from './hat_mishap'
import { idle } from './idle'
import { idleLiving } from './idle_living'
import { juggling } from './juggling'
import { blank, type AnimFn, type Grid } from './kit'
import { lowBattery } from './low_battery'
import { sleeping } from './sleeping'
import { sweeping } from './sweeping'
import { thinking } from './thinking'
import { typing } from './typing'
import { waitingReply } from './waiting_reply'
import { wake } from './wake'
import { wizard } from './wizard'

// One pixel pose function per firmware animation (assets/svg-animations/*.svg).
export const ANIMS: Record<AnimName, AnimFn> = {
  idle,
  idle_living: idleLiving,
  sleeping,
  wake,
  happy,
  thinking,
  typing,
  debugger: debuggerAnim,
  building,
  conducting,
  wizard,
  beacon,
  juggling,
  sweeping,
  confused,
  hat_mishap: hatMishap,
  dizzy,
  low_battery: lowBattery,
  alert,
  waiting_reply: waitingReply,
}

export function drawAnim(name: AnimName, f: number): Grid {
  const g = blank()
  ANIMS[name](g, f)
  return g
}
