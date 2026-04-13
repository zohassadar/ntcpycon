# [NESTrisChamps](https://github.com/nestrischamps/nestrischamps) Connector

Connector for NESTrisChamps that can receive game data from the following sources:

* [Everdrive](https://github.com/krikzz/edn8-pro-pub)
* [NESTrisOCR](https://github.com/alex-ong/NESTrisOCR) (needs work)


## setup

requires newish python (tested on 3.12+)

Use python virtual environment

```
pip install -e python-edlinkn8
pip install -e .
```


### create rooms.yml

see `rooms-example.yml`

### run server

```
ed2ntc server
```


### run client

```
ed2ntc client
```


## Nestrischamps

follow notes.txt and either start service or run `npm run start`
