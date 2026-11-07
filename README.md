# Données Prochains passages (2/2)

Horaires théoriques des transports en commun, préparés pour l'appli Android « Prochains passages ».

- Source : données ouvertes publiées sur [transport.data.gouv.fr](https://transport.data.gouv.fr) (licences ouvertes des réseaux).
- Le fichier `build/networks.json` liste les 244 réseaux de ce dépôt.
- La tâche GitHub Actions « Construire les horaires » télécharge les horaires officiels, les découpe par arrêt et les publie avec GitHub Pages, le 1er et le 15 de chaque mois (et à chaque modification du dossier `build`).
- Publication : https://max54130.github.io/passages-donnees-2/d/nets.json
