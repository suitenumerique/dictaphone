export default function LogoApp({
  height = 26,
  variant = 'single-line',
  alt = '',
}: {
  height?: number
  variant?: 'picto' | 'multiline' | 'single-line'
  alt?: string
}) {
  return (
    <div className="dictaphone__logo-app">
      <img
        src={`/assets/logo-${variant}.svg`}
        alt={alt}
        height={height}
        aria-hidden={true}
      />
    </div>
  )
}
