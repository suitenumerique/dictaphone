export default function LogoApp({
  size = 26,
  withLabel = false,
}: {
  size?: number
  withLabel?: boolean
}) {
  return (
    <div className="dictaphone__logo-app">
      <img
        src="/assets/logo-dictaphone-beta.svg"
        alt="Logo"
        width={size}
        height={size}
      />
      {withLabel && <span className="">Dictaphone</span>}
    </div>
  )
}
