export default function LogoApp({
  height = 26,
  variant = 'single-line',
}: {
  height?: number
  variant?: 'picto' | 'multiline' | 'single-line'
}) {
  return (
    <div className="dictaphone__logo-app">
      <img src={`/assets/logo-${variant}.svg`} alt="Logo" height={height} />
    </div>
  )
}
