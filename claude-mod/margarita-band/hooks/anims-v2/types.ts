// Shape of the data tools/svg2mod_frames.py generates (one V2Anim per animation).
export type V2Anim = {
  fps: number
  width: number // art pixels = text columns
  height: number // art pixels, always even (two pixel rows per text row)
  palette: string[] // '#RRGGBB'
  // [run-length encoded rows, hold]: hold = how many source frames (1/fps each) it lasts.
  frames: Array<[string, number]>
}
